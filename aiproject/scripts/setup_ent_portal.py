"""Explicit local-only portal migration/bootstrap; no existing accounts are reset."""
import argparse,base64,hashlib,json,re,secrets,shutil
from datetime import datetime,date,timedelta
from pathlib import Path
from sqlalchemy import MetaData,Table,select,insert,inspect,text
from sqlalchemy.orm import Session
from sqlalchemy.schema import CreateTable
from app.core.database import engine
from app.core.config import get_settings
from app.model_registry import register_models
from app.core.security.credentials import hash_password,utc_now
from app.core.security.rbac import ROLE_DEFAULTS
from app.modules.auth.models import AUTH_NEW_TABLES,role_permissions,student_scopes,roles
from app.ai.assistant.models import AI_NEW_TABLES
ROOT=Path(__file__).resolve().parents[1]
CREDENTIALS=ROOT/'logs/ent-portal-local-credentials.json'
MANIFEST=ROOT/'data/datasets/ent-portal-local-manifest.json'


def serial(value):
    if isinstance(value,bytes):return {'base64':base64.b64encode(value).decode()}
    if hasattr(value,'isoformat'):return value.isoformat()
    return str(value)


def backup():
    out=ROOT/'logs'/('portal-before-002-'+datetime.now().strftime('%Y%m%d-%H%M%S'))
    out.mkdir(parents=True,exist_ok=False)
    snapshot={};schema=[]
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn:
        with conn.begin():
            names=inspect(conn).get_table_names()
            for name in names:
                if not re.fullmatch(r'\w+',name):raise RuntimeError('Unexpected table name')
                t=Table(name,MetaData(),autoload_with=conn)
                snapshot[name]=[dict(r) for r in conn.execute(select(t)).mappings()]
                schema.append(conn.exec_driver_sql('SHOW CREATE TABLE '+chr(96)+name+chr(96)).one()[1]+';')
    data=json.dumps(snapshot,ensure_ascii=False,indent=2,default=serial).encode()
    (out/'snapshot.json').write_bytes(data)
    (out/'schema.sql').write_text('\n\n'.join(schema),encoding='utf-8')
    if (ROOT/'.env').exists():shutil.copy2(ROOT/'.env',out/'private-env-before.txt')
    info={'tables':len(snapshot),'row_counts':{k:len(v) for k,v in snapshot.items()},'sha256':hashlib.sha256(data).hexdigest()}
    (out/'manifest.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    return str(out)


def migrate():
    register_models();new=AUTH_NEW_TABLES+AI_NEW_TABLES
    old=set(inspect(engine).get_table_names())
    missing=[t for t in new if t.name not in old]
    backup_path=backup() if missing else None
    sql='\n\n'.join(str(CreateTable(t).compile(engine)).strip()+';' for t in new)
    (ROOT/'migrations/002_ent_portal_expected.sql').write_text(sql,encoding='utf-8')
    for t in missing:t.create(engine,checkfirst=True)
    if role_permissions.name not in old:
        with engine.begin() as conn:
            for role in conn.execute(select(roles)).mappings():
                grants=ROLE_DEFAULTS.get(role['role_code'],set())
                if grants:conn.execute(insert(role_permissions),[{'role_id':role['id'],'permission':p} for p in sorted(grants)])
    return {'backup':backup_path,'created_tables':[t.name for t in missing]}


def bootstrap():
    if CREDENTIALS.exists():
        saved=json.loads(CREDENTIALS.read_text(encoding='utf-8'))
    else:saved={'accounts':[]}
    known={a['username']:a for a in saved['accounts']}
    md=MetaData()
    tables={n:Table(n,md,autoload_with=engine) for n in ('sys_user','student_info','crm_lead','student_feedback_ticket','student_admin_service','todo_item')}
    users=tables['sys_user'];ids={};accounts_out=[];now=datetime.now()
    with engine.begin() as conn:
        role_map={r['role_code']:r['id'] for r in conn.execute(select(roles)).mappings()}
        for code,label in [('admin','联调管理员'),('employee','联调员工'),('manager','联调经理'),('team_leader','联调班主任')]:
            username={'team_leader':'ent_teacher'}.get(code,'ent_'+code)
            existing=conn.execute(select(users).where(users.c.username==username)).mappings().first()
            if existing:
                if username not in known:raise RuntimeError('Bootstrap account exists but its credential file is missing: '+username)
                rid=existing['id'];entry=known[username]
            else:
                password=secrets.token_urlsafe(18)
                rid=conn.execute(insert(users).values(username=username,password_hash=hash_password(password),real_name=label,
                    user_type='admin' if code=='admin' else 'employee',role_id=role_map[code],department='ENT本地联调',
                    contact_info=username+'@example.invalid',status='normal',create_time=now,update_time=now)).inserted_primary_key[0]
                entry={'username':username,'password':password,'role':code,'name':label}
            entry['id']=rid;ids[code]=rid;accounts_out.append(entry)
        student_ids=[]
        for suffix,label in [('a','联调学生甲'),('b','联调学生乙')]:
            username='ent_portal_student_'+suffix
            existing=conn.execute(select(users.c.id).where(users.c.username==username)).scalar_one_or_none()
            if existing is None:
                sid=conn.execute(insert(users).values(username=username,password_hash=hash_password(secrets.token_urlsafe(24)),real_name=label,
                    user_type='student',role_id=role_map['student'],department='ENT本地联调',status='normal',create_time=now,update_time=now)).inserted_primary_key[0]
                conn.execute(insert(tables['student_info']).values(user_id=sid,student_no='ENTPORTAL-'+suffix.upper(),
                    school='本地合成验证数据',major='接口联调',class_teacher_id=ids['team_leader'],status='active',enroll_date=date.today()))
            else:sid=existing
            student_ids.append(sid)
        for uid in (ids['admin'],ids['team_leader']):
            for sid in student_ids:
                if not conn.execute(select(student_scopes).where(student_scopes.c.user_id==uid,student_scopes.c.student_id==sid)).first():
                    conn.execute(insert(student_scopes).values(user_id=uid,student_id=sid))
        demo={}
        for code,uid in ids.items():
            marker='ENT门户联调-'+code
            lead=conn.execute(select(tables['crm_lead'].c.id).where(tables['crm_lead'].c.owner_employee_id==uid,tables['crm_lead'].c.customer_name==marker)).scalar_one_or_none()
            if lead is None:
                lead=conn.execute(insert(tables['crm_lead']).values(customer_name=marker,owner_employee_id=uid,contact_info=code+'@example.invalid',
                    intended_country='英国',background_info='仅用于本机合成联调验证',status='new',create_time=now,update_time=now)).inserted_primary_key[0]
            ticket=conn.execute(select(tables['student_feedback_ticket'].c.id).where(tables['student_feedback_ticket'].c.title==marker)).scalar_one_or_none()
            if ticket is None:
                ticket=conn.execute(insert(tables['student_feedback_ticket']).values(student_id=student_ids[0],ticket_type='consult',title=marker,
                    content='本机合成数据：请协助验证工单处理',assignee_id=uid,status='pending',priority='medium',is_notified=0,create_time=now,update_time=now)).inserted_primary_key[0]
            leave=conn.execute(select(tables['student_admin_service'].c.id).where(tables['student_admin_service'].c.reason==marker)).scalar_one_or_none()
            if leave is None:
                leave=conn.execute(insert(tables['student_admin_service']).values(student_id=student_ids[0],service_type='leave',leave_type='personal',
                    start_time=now+timedelta(days=1),end_time=now+timedelta(days=2),reason=marker,approver_id=uid,status='pending',create_time=now,update_time=now)).inserted_primary_key[0]
            todo=conn.execute(select(tables['todo_item'].c.id).where(tables['todo_item'].c.assignee_id==uid,tables['todo_item'].c.title==marker)).scalar_one_or_none()
            if todo is None:
                todo=conn.execute(insert(tables['todo_item']).values(assignee_id=uid,todo_type='custom',title=marker,description='体验待办与AI联动',
                    status='pending',priority='medium',due_time=now-timedelta(hours=1),create_time=now,update_time=now)).inserted_primary_key[0]
            demo[code]={'lead_id':lead,'ticket_id':ticket,'leave_id':leave,'todo_id':todo}
    # This file is private and ignored. No password is printed to stdout.
    saved.update(accounts=accounts_out,login_url='http://127.0.0.1:5173',api_url='http://127.0.0.1:8002')
    CREDENTIALS.parent.mkdir(parents=True,exist_ok=True)
    CREDENTIALS.write_text(json.dumps(saved,ensure_ascii=False,indent=2),encoding='utf-8')
    result={'accounts':[{k:a[k] for k in ('id','username','role','name')} for a in accounts_out],
            'student_ids':student_ids,'demo':demo,'credential_file':str(CREDENTIALS)}
    MANIFEST.parent.mkdir(parents=True,exist_ok=True);MANIFEST.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def configure():
    path=ROOT/'.env';current=path.read_text(encoding='utf-8') if path.exists() else ''
    if not re.search(r'^AUTH_JWT_SECRET\s*=',current,re.M):
        current+='\n# ENT portal signing key; do not commit this file.\nAUTH_JWT_SECRET='+secrets.token_urlsafe(48)+'\n'
        path.write_text(current,encoding='utf-8')


def main():
    p=argparse.ArgumentParser();p.add_argument('--bootstrap',action='store_true');args=p.parse_args()
    s=get_settings()
    if s.db_host not in ('127.0.0.1','localhost','::1') or s.db_name!='education_service':
        raise SystemExit('This setup is restricted to the existing local education_service database')
    result=migrate();configure()
    if args.bootstrap:
        result['bootstrap']=bootstrap()
        from app.modules.todo.reminders import scan_reminders
        with Session(engine) as db:
            result['reminders']=scan_reminders(db,employee_ids=[a['id'] for a in result['bootstrap']['accounts']])
    print(json.dumps(result,ensure_ascii=False,default=serial))

if __name__=='__main__':main()
