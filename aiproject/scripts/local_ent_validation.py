"""Localhost-only schema audit and additive synthetic fixtures; never executes DDL.
Check: python -m scripts.local_ent_validation
Seed: python -m scripts.local_ent_validation --seed --verify --date 2026-11-11
"""
import argparse
import hashlib
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from sqlalchemy import MetaData, select, text, func
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import engine

ROOT = Path(__file__).resolve().parents[1]
SQL_FILE = ROOT.parent / '教育服务_0914' / '2222通过表可以实现curd' / 'db_init.sql'
MARKER = 'ENT_LOCAL_VERIFY_V1'
REPORT = ROOT / 'docs' / '回复Cursor' / 'runs' / 'local-ent-validation-latest.json'


def digest(rows):
    return hashlib.sha256(json.dumps(rows,ensure_ascii=False,sort_keys=True,default=str).encode()).hexdigest()


def normalized(value):
    return re.sub(r'\s+', '', str(value or '').lower()).replace('current_timestamp()', 'current_timestamp')


def normalized_default(value):
    if value is None:
        return None
    raw = str(value)
    if normalized(raw) in ("current_timestamp", "current_timestamp()"):
        return "current_timestamp"
    return raw


def audit(conn):
    sql = SQL_FILE.read_text(encoding='utf-8-sig')
    definitions = dict(re.findall(r'CREATE TABLE \x60([^\x60]+)\x60\s*\((.*?)\)\s*ENGINE', sql, re.S|re.I))
    if not definitions:
        raise RuntimeError("No standard CREATE TABLE definitions parsed")
    actual = {r.TABLE_NAME:dict(r._mapping) for r in conn.execute(text("SELECT TABLE_NAME,ENGINE,TABLE_COLLATION FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_TYPE='BASE TABLE'"))}
    overlay = ROOT / 'migrations' / '001_ent_reliability_expected.sql'
    migration_hash = None
    if 'student_score_history' in actual:
        overlay_sql = overlay.read_text(encoding='utf-8')
        definitions.update(dict(re.findall(r'CREATE TABLE \x60([^\x60]+)\x60\s*\((.*?)\)\s*ENGINE', overlay_sql, re.S|re.I)))
        migration_hash = hashlib.sha256(overlay_sql.encode()).hexdigest()
    differences = []
    for table, definition in definitions.items():
        if table not in actual:
            differences.append({'table':table,'missing_table':True})
            continue
        columns = {r.COLUMN_NAME:dict(r._mapping) for r in conn.execute(text('SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLUMN_DEFAULT,EXTRA FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:t ORDER BY ORDINAL_POSITION'),{'t':table})}
        expected_columns = []
        expected_indexes = {}
        for raw in definition.splitlines():
            line = raw.strip().rstrip(',')
            match = re.match(r'\x60([^\x60]+)\x60\s+((?:enum\([^)]*\)|\w+(?:\([^)]*\))?)(?:\s+UNSIGNED)?)\s*(.*)',line,re.I)
            if match:
                name,dtype,attrs = match.groups()
                expected_columns.append(name)
                if name not in columns:
                    differences.append({'table':table,'column':name,'missing':True})
                    continue
                got = columns[name]
                match_default = re.search(r"\bDEFAULT\s+('(?:[^']|'')*'|CURRENT_TIMESTAMP(?:\(\))?|NULL|-?\d+(?:\.\d+)?)",attrs,re.I)
                default = match_default.group(1).strip("'") if match_default else None
                if default and default.upper() == 'NULL':
                    default = None
                expected = {'type':normalized(dtype),'nullable':'NO' if 'NOT NULL' in attrs.upper() else 'YES','default':normalized_default(default),'auto_increment':'AUTO_INCREMENT' in attrs.upper(),'on_update':'ON UPDATE CURRENT_TIMESTAMP' in attrs.upper()}
                observed = {'type':normalized(got['COLUMN_TYPE']),'nullable':got['IS_NULLABLE'],'default':normalized_default(got['COLUMN_DEFAULT']),'auto_increment':'auto_increment' in got['EXTRA'].lower(),'on_update':'on update current_timestamp' in got['EXTRA'].lower()}
                if expected != observed:
                    differences.append({'table':table,'column':name,'expected':expected,'actual':observed})
                continue
            match = re.match(r'(?:(PRIMARY) KEY|(UNIQUE|FULLTEXT)?\s*KEY\s+\x60([^\x60]+)\x60)\s*\(([^)]+)\)',line,re.I)
            if match:
                primary,kind,name,cols = match.groups()
                name = 'PRIMARY' if primary else name
                expected_indexes[name] = {'columns':re.findall(r'\x60([^\x60]+)\x60',cols),'unique':bool(primary or kind=='UNIQUE'),'type':'FULLTEXT' if kind=='FULLTEXT' else 'BTREE'}
        for name in set(columns)-set(expected_columns):
            differences.append({'table':table,'extra_column':name})
        got_indexes = {}
        for r in conn.execute(text('SELECT INDEX_NAME,COLUMN_NAME,NON_UNIQUE,INDEX_TYPE FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=:t ORDER BY INDEX_NAME,SEQ_IN_INDEX'),{'t':table}):
            item = got_indexes.setdefault(r.INDEX_NAME,{'columns':[],'unique':not bool(r.NON_UNIQUE),'type':r.INDEX_TYPE})
            item['columns'].append(r.COLUMN_NAME)
        if expected_indexes != got_indexes:
            differences.append({'table':table,'indexes_expected':expected_indexes,'indexes_actual':got_indexes})
        if actual[table]['ENGINE'] != 'InnoDB' or actual[table]['TABLE_COLLATION'] != 'utf8mb4_unicode_ci':
            differences.append({'table':table,'storage':actual[table]})
    counts = {t:conn.execute(text('SELECT COUNT(*) FROM '+chr(96)+t.replace(chr(96),chr(96)*2)+chr(96))).scalar_one() for t in sorted(actual)}
    return {'standard_sql':str(SQL_FILE),'standard_sha256':hashlib.sha256(sql.encode()).hexdigest(),'migration_expected_sha256':migration_hash,'expected_table_count':len(definitions),'actual_table_count':len(actual),'missing_tables':sorted(set(definitions)-set(actual)),'extra_tables':sorted(set(actual)-set(definitions)),'checked_dimensions':['columns','types','nullability','defaults','auto_increment','on_update','indexes','engine','collation'],'differences':differences,'table_counts':counts}


def snapshot(conn,metadata):
    return {name:{row.id:dict(row._mapping) for row in conn.execute(select(table).order_by(table.c.id))} for name,table in metadata.tables.items()}


def preserve_existing(conn,metadata,before):
    for name,rows in before.items():
        if rows:
            table=metadata.tables[name]
            current={row.id:dict(row._mapping) for row in conn.execute(select(table).where(table.c.id.in_(rows)).order_by(table.c.id))}
            assert digest(current)==digest(rows), 'Existing rows changed: '+name


def data_integrity(conn):
    references = {
        "sys_user": [("role_id", "sys_role")],
        "sys_organization": [("manager_id", "sys_user")],
        "crm_lead": [("owner_employee_id", "sys_user")],
        "crm_follow_up": [("employee_id", "sys_user"), ("lead_id", "crm_lead")],
        "student_info": [("user_id", "sys_user"), ("class_teacher_id", "sys_user")],
        "employee_daily_report": [("employee_id", "sys_user")],
        "student_score": [("student_id", "sys_user"), ("recorded_by", "sys_user")],
        "student_admin_service": [("student_id", "sys_user"), ("approver_id", "sys_user")],
        "student_feedback_ticket": [("student_id", "sys_user"), ("assignee_id", "sys_user")],
        "todo_item": [("assignee_id", "sys_user")],
        "notification_log": [("user_id", "sys_user")],
    }
    if 'student_score_history' in __import__('sqlalchemy').inspect(conn).get_table_names():
        references['student_score_history'] = [('score_id', 'student_score'), ('changed_by', 'sys_user')]
    gaps = []
    for table, columns in references.items():
        for column, target in columns:
            query = f"SELECT s.{column} AS missing_id,COUNT(*) AS affected_rows FROM {table} s LEFT JOIN {target} t ON s.{column}=t.id WHERE s.{column} IS NOT NULL AND t.id IS NULL GROUP BY s.{column}"
            for row in conn.execute(text(query)):
                gaps.append({"table": table, "column": column, "target": target, **dict(row._mapping)})
    return {"checked": "ENT user, role, student and CRM references", "gaps": gaps, "auto_repaired": False}


def check_scanner_sources(db, expected):
    from app.modules.todo.models import todo_item
    actual = {}
    for source, source_id in expected:
        count = db.execute(select(func.count()).select_from(todo_item).where(todo_item.c.related_type == source, todo_item.c.related_id == source_id)).scalar_one()
        if count != 1:
            raise AssertionError(f"Expected exactly one todo for {source}/{source_id}; got {count}")
        actual[f"{source}/{source_id}"] = count
    return actual


def complete_legacy_demo_users(conn, metadata):
    """Explicitly authorized placeholders for historical local fixture IDs 1 and 2."""
    users = metadata.tables['sys_user']
    role = conn.execute(text("SELECT id FROM sys_role WHERE role_code='employee'")).scalar_one()
    planned = []
    for employee_id in (1, 2):
        username = f"ENT_LEGACY_DEMO_EMPLOYEE_{employee_id}"
        row = conn.execute(select(users).where(users.c.id == employee_id)).mappings().first()
        if row:
            if row['username'] != username or row['user_type'] != 'employee' or row['status'] != 'disabled' or row['password_hash'] != '!ENT_LEGACY_NO_LOGIN!':
                raise RuntimeError(f"ID {employee_id} is occupied by a different user; refusing to overwrite")
        else:
            if conn.execute(select(users.c.id).where(users.c.username == username)).first():
                raise RuntimeError(f"Placeholder username conflict for ID {employee_id}")
            planned.append(dict(id=employee_id, username=username, password_hash='!ENT_LEGACY_NO_LOGIN!', real_name=f"历史测试员工{employee_id}（占位）", user_type='employee', role_id=role, department='历史测试数据占位', contact_info=None, status='disabled'))
    for values in planned:
        conn.execute(users.insert().values(**values))
    customer_counts = dict(conn.execute(text("SELECT l.owner_employee_id,COUNT(*) FROM crm_lead l JOIN sys_user u ON u.id=l.owner_employee_id AND u.user_type='employee' WHERE l.owner_employee_id IN (1,2) GROUP BY l.owner_employee_id")).all())
    follow_count = conn.execute(text("SELECT COUNT(*) FROM crm_follow_up f JOIN sys_user u ON u.id=f.employee_id AND u.user_type='employee' WHERE f.employee_id IN (1,2)")).scalar_one()
    return {'created_total': len(planned), 'ids': [1,2], 'status': 'disabled', 'usable_login': False, 'synthetic_placeholders': True, 'linked_customer_counts': customer_counts, 'linked_follow_up_count': follow_count}


def seed(conn,metadata,day):
    ids,created={},{}
    now=datetime.combine(day,datetime.min.time()).replace(hour=10)
    def add(table,key,lookup,**values):
        obj=metadata.tables[table]
        stmt=select(obj.c.id)
        for column,value in lookup.items():
            stmt=stmt.where(obj.c[column]==value)
        matches=conn.execute(stmt).scalars().all()
        if len(matches)>1:
            raise RuntimeError('Ambiguous fixture key: '+table+'/'+key)
        if matches:
            rid=matches[0]
        else:
            rid=conn.execute(obj.insert().values(**lookup,**values)).inserted_primary_key[0]
            created[table]=created.get(table,0)+1
        ids[key]=rid
        return rid
    roles=dict(conn.execute(text('SELECT role_code,id FROM sys_role')).all())
    assert {'employee','student'} <= roles.keys(), 'Missing standard roles'
    existing=snapshot(conn,metadata)
    highest=max((value for rows in existing.values() for row in rows.values() for column,value in row.items() if (column=='id' or column.endswith('_id')) and isinstance(value,int)),default=0)
    fixture_id_floor=max(1_000_000,highest+1000)
    for ordinal,(key,kind,label,status) in enumerate([
        ('employee_a','employee','验证顾问甲','normal'),
        ('employee_b','employee','验证顾问乙','normal'),
        ('employee_disabled','employee','验证停用员工','disabled'),
        ('student_a','student','验证学生甲','normal'),
        ('student_b','student','验证学生乙','normal'),
        ('student_disabled','student','验证停用学生','disabled'),
    ],start=1):
        add('sys_user',key,{'username':MARKER+'_'+key},id=fixture_id_floor+ordinal,password_hash='!ENT_TEST_NO_LOGIN!',real_name=label,user_type=kind,role_id=roles[kind],department=MARKER+'_教学验证部',contact_info=key+'@example.invalid',status=status)
    a,b,sa,sb=(ids[k] for k in ('employee_a','employee_b','student_a','student_b'))
    company=add('sys_organization','org_company',{'org_name':MARKER+'_虚构公司'},org_level=1,manager_id=a)
    for key,label,owner,status in [('org_a','验证教学部',a,1),('org_b','验证咨询部',b,1),('org_disabled','停用验证部门',a,0)]:
        add('sys_organization',key,{'org_name':MARKER+'_'+label},parent_id=company,org_level=2,manager_id=owner,status=status)
    for key,status,topic in [('guide_entry',1,'入职操作演示'),('guide_crm',1,'客户跟进演示'),('guide_leave',1,'请假审批演示'),('guide_disabled',0,'停用指引演示')]:
        add('onboarding_guide',key,{'title':MARKER+'_'+topic},category='测试演示',content=MARKER+'：此条仅供接口验证，属于虚构演示资料，不是公司的真实制度。'+topic,status=status)
    for key in ('student_a','student_b','student_disabled'):
        add('student_info','info_'+key,{'user_id':ids[key]},student_no=MARKER+'_'+key[-8:],school='虚构验证学校',major='测试专业',grade='2026',class_teacher_id=b if key=='student_b' else a,status='suspended' if key=='student_disabled' else 'active')
    for i,(owner,status,label) in enumerate([(a,'new','新客户'),(a,'contacting','联系中'),(a,'qualified','已研判'),(a,'signed','已签约'),(a,'lost','已流失'),(a,'new','同名客户'),(a,'new','同名客户'),(b,'new','乙方客户')]):
        key='lead_'+str(i)
        rid=add('crm_lead',key,{'remark':MARKER+':'+key},customer_name=MARKER+'_'+label,contact_info=key+'@example.invalid',education_level='本科（虚构）',intended_country='示例国家',intended_major='测试专业',source_channel='local_test',owner_employee_id=owner,status=status,lost_reason='虚构验证：暂不考虑' if status=='lost' else None,background_info=MARKER+' 虚构数据，不用于真实业务')
        if i in (1,2,3,7):
            add('crm_follow_up','follow_'+str(i),{'lead_id':rid,'content':MARKER+':follow_'+str(i)},employee_id=owner,follow_type='other',next_plan='仅用于测试，不自动联系客户')
    for employee in ('employee_a','employee_b'):
        for offset in (0,1):
            add('employee_daily_report','report_'+employee+str(offset),{'employee_id':ids[employee],'report_date':day-timedelta(days=offset)},raw_content=MARKER+' 虚构日报原文',content=MARKER+' 完成客户录入和跟进验证',key_progress=['验证数据，不是真实绩效'],risks=['仅用于本地测试'],next_plan='验证接口与权限',status='submitted')
    for i,(student,owner,value) in enumerate([(sa,a,'85.50'),(sa,a,'92.00'),(sb,b,'78.25'),(ids['student_disabled'],a,'60.00')]):
        add('student_score','score_'+str(i),{'student_id':student,'course_name':MARKER+'_课程'+str(i),'semester':'2026-2027-1'},score=value,credit='2.0',recorded_by=owner)
    for i,(student,owner,status) in enumerate([(sa,a,'pending'),(sb,b,'pending'),(sa,None,'pending'),(sa,a,'approved'),(sa,a,'rejected'),(sa,a,'pending')]):
        add('student_admin_service','leave_'+str(i),{'reason':MARKER+':leave_'+str(i)},student_id=student,service_type='leave',leave_type='personal',start_time=now+timedelta(days=1),end_time=now+timedelta(days=2),status=status,approver_id=owner,approval_comment='虚构已处理单据' if status!='pending' else None,approval_time=now if status!='pending' else None)
    for i,(student,owner,status) in enumerate([(sa,a,'pending'),(sa,a,'processing'),(sa,a,'resolved'),(sa,a,'closed'),(sb,b,'pending'),(sa,None,'pending')]):
        add('student_feedback_ticket','ticket_'+str(i),{'title':MARKER+':ticket_'+str(i)},student_id=student,ticket_type='complaint',category='虚构验证',content=MARKER+' 虚构投诉，不代表真实客户意见',status=status,assignee_id=owner,solution='虚构验证：已确认处理方案' if status in ('resolved','closed') else None,is_notified=0)
    for i,(owner,status,offset) in enumerate([(a,'pending',-1),(a,'in_progress',1),(a,'done',-2),(b,'pending',-1),(a,'cancelled',-1)]):
        add('todo_item','todo_'+str(i),{'title':MARKER+':todo_'+str(i)},assignee_id=owner,todo_type='custom',description=MARKER+' 虚构待办，无外部推送',status=status,due_time=now+timedelta(days=offset),completed_time=now if status=='done' else None)
    for i,owner in enumerate((a,a,b)):
        add('notification_log','notice_'+str(i),{'title':MARKER+':notice_'+str(i)},user_id=owner,notification_type='local_test',content=MARKER+' 站内测试消息；未向微信、短信或邮件发送',channel='system',status='sent')
    return {'marker':MARKER,'date':str(day),'ids':ids,'created_counts':created,'created_total':sum(created.values()),'accounts_have_no_usable_password':True}


def verify(conn,fixtures):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.core.database import get_db
    from app.core.security import EmployeePrincipal,require_employee
    from app.router_registry import register_routers
    from app.modules.todo.reminders import scan_reminders
    ids=fixtures['ids']
    a,b,sa,sb=(ids[k] for k in ('employee_a','employee_b','student_a','student_b'))
    app=FastAPI()
    register_routers(app)
    outcomes=[]
    # Route commits only release SAVEPOINTs; the enclosing transaction is rolled back.
    with Session(bind=conn,join_transaction_mode='create_savepoint',expire_on_commit=False) as db:
        app.dependency_overrides[get_db]=lambda:db
        app.dependency_overrides[require_employee]=lambda:EmployeePrincipal(a,frozenset({'directory:contacts','scores:read','scores:write','guides:write','crm:read','crm:write','reports:read','leaves:read','leaves:approve'}),frozenset({sa}))
        with TestClient(app) as client:
            def call(label,method,url,status=200,**kwargs):
                response=client.request(method,url,**kwargs)
                assert response.status_code==status,(label,response.status_code,response.text)
                outcomes.append({'case':label,'status':response.status_code})
                return response.json()
            orgs=call('组织检索','GET','/api/v1/enterprise/organizations',params={'keyword':MARKER})['data']
            assert ids['org_a'] in {r['id'] for r in orgs} and ids['org_disabled'] not in {r['id'] for r in orgs}
            call('员工联系方式','GET',f'/api/v1/enterprise/colleagues/{a}/contact')
            guides=call('指南检索','GET','/api/v1/enterprise/onboarding-guides',params={'keyword':MARKER})['data']
            assert ids['guide_entry'] in {r['id'] for r in guides} and ids['guide_disabled'] not in {r['id'] for r in guides}
            rows=call('本人成绩查询','GET',f'/api/v1/enterprise/scores?student_id={sa}')['data']
            assert {ids['score_0'],ids['score_1']} <= {r['id'] for r in rows}
            call('越范围成绩拒绝','GET',f'/api/v1/enterprise/scores?student_id={sb}',403)
            call('成绩写入','POST','/api/v1/enterprise/scores',json={'student_id':sa,'course_name':MARKER+'_rollback','score':'88.25','semester':'2026-2027-1'})
            call('成绩更正','PUT',f"/api/v1/enterprise/scores/{ids['score_0']}",json={'student_id':sa,'course_name':MARKER+'_课程0','score':'89.50','semester':'2026-2027-1'})
            disabled = ids['student_disabled']
            app.dependency_overrides[require_employee]=lambda:EmployeePrincipal(a,frozenset({'directory:contacts','scores:read','scores:write','guides:write','crm:read','crm:write','reports:read','leaves:read','leaves:approve'}),frozenset({sa,disabled}))
            call('停用学生成绩录入拒绝','POST','/api/v1/enterprise/scores',422,json={'student_id':disabled,'course_name':MARKER+'_rollback','score':'88.25'})
            call('停用学生成绩更正拒绝','PUT',f"/api/v1/enterprise/scores/{ids['score_3']}",422,json={'student_id':disabled,'course_name':MARKER+'_课程3','score':'89.50'})
            app.dependency_overrides[require_employee]=lambda:EmployeePrincipal(a,frozenset({'directory:contacts','scores:read','scores:write','guides:write','crm:read','crm:write','reports:read','leaves:read','leaves:approve'}),frozenset({sa}))
            leads=call('客户范围','GET','/api/v1/consultant/leads')['data']['items']
            assert leads and all(r['owner_employee_id']==a for r in leads)
            call('他人客户拒绝','GET',f"/api/v1/consultant/leads/{ids['lead_7']}",403)
            call('同名客户冲突','POST','/api/v1/ai/nl2sql/query',409,json={'intent':'lead_detail_by_name','params':{'customer_name':MARKER+'_同名客户'}})
            call('客户状态更新','PATCH',f"/api/v1/consultant/leads/{ids['lead_0']}/status",json={'status':'contacting'})
            call('客户跟进写入','POST',f"/api/v1/consultant/leads/{ids['lead_0']}/follow-ups",json={'employee_id':a,'content':MARKER+'_rollback','follow_type':'other'})
            reports=call('本人日报查询','GET','/api/v1/employee-reports')['data']
            assert reports and all(r['employee_id']==a for r in reports)
            call('日报写入','POST','/api/v1/employee-reports',json={'employee_id':a,'report_date':fixtures['date'],'content':MARKER+'_rollback'})
            call('他人日报拒绝','GET',f'/api/v1/employee-reports?employee_id={b}',403)
            leaves=call('请假审批范围','GET','/api/v1/student-admin/leaves/pending')['data']
            assert {r['id'] for r in leaves}=={ids['leave_0'],ids['leave_5']}
            for key,label in [('leave_1','他人请假拒绝'),('leave_2','未分配请假拒绝')]:
                call(label,'POST',f"/api/v1/student-admin/leaves/{ids[key]}/approve",403,json={'approver_id':a,'decision':'approved'})
            call('本人请假审批','POST',f"/api/v1/student-admin/leaves/{ids['leave_0']}/approve",json={'approver_id':a,'decision':'approved'})
            call('重复请假审批拒绝','POST',f"/api/v1/student-admin/leaves/{ids['leave_0']}/approve",409,json={'approver_id':a,'decision':'approved'})
            call('他人工单拒绝','GET',f"/api/v1/enterprise/tickets/{ids['ticket_4']}",403)
            for code in (200,409):
                call('投诉流转' if code==200 else '投诉陈旧状态拒绝','PATCH',f"/api/v1/enterprise/tickets/{ids['ticket_0']}",code,json={'expected_status':'pending','status':'processing'})
            call('待办到期查询','GET','/api/v1/enterprise/todos?due_only=true')
            call('待办完成','PATCH',f"/api/v1/enterprise/todos/{ids['todo_0']}",json={'expected_status':'pending','status':'done'})
            call('他人待办拒绝','PATCH',f"/api/v1/enterprise/todos/{ids['todo_3']}",403,json={'expected_status':'pending','status':'done'})
            notices=call('站内通知范围','GET','/api/v1/enterprise/notifications')['data']
            assert notices and all(r['user_id']==a for r in notices)
            scanned=scan_reminders(db, employee_ids=frozenset({a,b}))
            assert scanned['todos_created']>0
            expected = [("student_admin_service", ids["leave_1"]), ("student_admin_service", ids["leave_5"])] + [("student_feedback_ticket", ids[k]) for k in ("ticket_0", "ticket_1", "ticket_4")]
            first_sources = check_scanner_sources(db, expected)
            repeated=scan_reminders(db, employee_ids=frozenset({a,b}))
            second_sources = check_scanner_sources(db, expected)
            assert first_sources == second_sources
            outcomes.append({'case':'真实MySQL扫描与重复扫描去重','first':scanned,'second':repeated,'fixture_source_counts':second_sources})
            del app.dependency_overrides[require_employee]
            call('正常身份仍默认拒绝','GET','/api/v1/enterprise/organizations',503)
        app.dependency_overrides.clear()
    return {'transport':'isolated FastAPI TestClient/ASGI','database':'real localhost MySQL','identity':'test-only dependency override, not real JWT','mutation_policy':'all API and scanner writes rolled back by outer transaction','checks':outcomes,'passed':len(outcomes)}


def main():
    global REPORT
    if not __debug__:
        raise SystemExit('Optimized Python disables validation assertions; refusing to run')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',default=str(REPORT))
    parser.add_argument('--seed',action='store_true')
    parser.add_argument('--verify',action='store_true')
    parser.add_argument('--complete-legacy-demo-users',action='store_true',help='Add disabled synthetic placeholders for historical local employee IDs 1 and 2')
    parser.add_argument('--date',type=date.fromisoformat,default=date(2026,11,11))
    args=parser.parse_args()
    REPORT=Path(args.output)
    if args.complete_legacy_demo_users and not args.seed:
        parser.error('--complete-legacy-demo-users requires --seed')
    if args.verify and not args.seed:

        parser.error('--verify requires --seed (idempotent)')
    settings=get_settings()
    if settings.db_host not in ('127.0.0.1','localhost','::1'):
        raise SystemExit('Refusing non-local database')
    if settings.employee_identity_mode!='blocked':
        raise SystemExit('Expected blocked production authentication')
    report={'date':str(args.date),'connection':{'host':settings.db_host,'port':settings.db_port,'database':settings.db_name},'ddl_executed':False}
    REPORT.parent.mkdir(parents=True,exist_ok=True)
    try:
        with engine.connect() as conn:
            report['server']=dict(conn.execute(text('SELECT DATABASE() AS db,@@hostname AS hostname,@@port AS port,VERSION() AS version,NOW() AS server_now')).mappings().one())
            report['schema']=audit(conn)
            if not report['schema']['missing_tables']:
                report['data_integrity']=data_integrity(conn)
            conn.rollback()
            if report['schema']['differences'] or report['schema']['missing_tables']:
                REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
                raise SystemExit('Schema differences found; report saved, no fixture writes')
            if args.seed:
                lock_name=MARKER+'_'+settings.db_name
                assert conn.execute(text('SELECT GET_LOCK(:name,5)'),{'name':lock_name}).scalar_one()==1
                conn.commit()
                try:
                    metadata=MetaData()
                    metadata.reflect(conn)
                    conn.rollback()
                    with conn.begin():
                        before=snapshot(conn,metadata)
                        if args.complete_legacy_demo_users:
                            report['legacy_completion']=complete_legacy_demo_users(conn,metadata)
                        fixtures=seed(conn,metadata,args.date)
                        preserve_existing(conn,metadata,before)
                    report['fixtures']=fixtures
                    report['existing_rows_preserved']=True
                    if args.verify:
                        with conn.begin():
                            seeded=snapshot(conn,metadata)
                        outer=conn.begin()
                        try:
                            report['verification']=verify(conn,fixtures)
                        finally:
                            outer.rollback()
                        with conn.begin():
                            preserve_existing(conn,metadata,seeded)
                            after=snapshot(conn,metadata)
                            assert {k:set(v) for k,v in seeded.items()}=={k:set(v) for k,v in after.items()},'Verification left inserted records'
                        report['verification']['rollback_confirmed']=True
                    with conn.begin():
                        report['after_table_counts']=audit(conn)['table_counts']
                        report['data_integrity_before']=report.get('data_integrity')
                        report['data_integrity']=data_integrity(conn)
                finally:
                    conn.execute(text('SELECT RELEASE_LOCK(:name)'),{'name':lock_name})
                    conn.commit()
    except BaseException as exc:
        report['status']='failed'
        report['error_type']=type(exc).__name__
        report['error']=str(exc)
        REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
        raise
    report['status']='passed_with_data_gaps' if report.get('data_integrity',{}).get('gaps') else 'passed'
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps({'report':str(REPORT),'status':report['status'],'data_gap_groups':len(report.get('data_integrity',{}).get('gaps',[])),'schema_differences':len(report['schema']['differences']),'created_total':report.get('fixtures',{}).get('created_total',0),'legacy_created_total':report.get('legacy_completion',{}).get('created_total',0),'verification_passed':report.get('verification',{}).get('passed',0)},ensure_ascii=False))


if __name__=='__main__':
    main()
