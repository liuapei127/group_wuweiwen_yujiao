"""Real spawned-process MySQL verification; only accepts an ent_verify_ database.
Run after preparing the isolated schema and fixtures:
python -m scripts.verify_ent_concurrency --database ent_verify_reliability_xxx
"""
import argparse
import json
import multiprocessing as mp
import os
import queue
import re
import uuid
from pathlib import Path
from sqlalchemy import create_engine,select,text,insert,update
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import engine as configured_engine
from app.core.security import EmployeePrincipal
from app.core.exceptions import BusinessError
from app.modules.consultant.errors import ConflictError
from app.modules.score.schemas import ScoreCreate,ScoreCorrection
from app.modules.score import service as score_service
from app.modules.student_admin.schemas import LeaveApprove
from app.modules.student_admin.service import StudentAdminServiceLayer
from app.modules.student_admin.models import StudentAdminService
from app.modules.todo.reminders import scan_reminders
from app.modules.todo.synchronization import synchronize_source
from app.modules.todo.models import todo_item,notification_log
from app.modules.feedback.models import student_feedback_ticket
from app.modules.score.models import student_score,student_score_history
from app.shared.utils.time_util import now_naive

ROOT=Path(__file__).resolve().parents[1]


def make_engine(database):
    settings=get_settings()
    if settings.db_host not in ('127.0.0.1','localhost','::1') or not re.fullmatch(r'ent_verify_[a-z0-9_]+',database):
        raise RuntimeError('Only explicitly isolated localhost ent_verify_ databases are allowed')
    return create_engine(configured_engine.url.set(database=database),pool_pre_ping=True,connect_args={'connect_timeout':5})


def worker(database,barrier,output,job):
    e=None
    try:
        e=make_engine(database)
        with e.connect() as c:
            connection_id=c.execute(text('SELECT CONNECTION_ID()')).scalar_one()
        barrier.wait(timeout=20)
        with Session(e,expire_on_commit=False) as db:
            p=EmployeePrincipal(job['employee'],frozenset({'scores:write','scores:read'}),frozenset({job['student']}))
            operation=job['operation']
            if operation=='scan':
                data=scan_reminders(db)
            elif operation=='create':
                data=score_service.create_score(ScoreCreate(**job['body']),db,p)
            elif operation=='correct':
                data=score_service.correct_score(job['score_id'],ScoreCorrection(**job['body']),db,p)
            elif operation=='approve':
                row=StudentAdminServiceLayer(db).approve_leave(job['leave_id'],LeaveApprove(approver_id=p.employee_id,decision='approved'))
                data={'id':row.id,'status':row.status}
            elif operation=='reassign':
                db.execute(update(student_feedback_ticket).where(student_feedback_ticket.c.id==job['ticket_id']).values(assignee_id=job['new_owner']))
                synchronize_source(db,'student_feedback_ticket',job['ticket_id'])
                db.commit();data={'assignee_id':job['new_owner']}
            else:
                raise ValueError(operation)
        output.put({'pid':os.getpid(),'connection_id':connection_id,'operation':operation,'status':200,'data':data})
    except (BusinessError,ConflictError) as exc:
        output.put({'pid':os.getpid(),'operation':job['operation'],'status':getattr(exc,'status_code',409),'error':str(exc)})
    except BaseException as exc:
        output.put({'pid':os.getpid(),'operation':job['operation'],'status':500,'error':repr(exc)})
    finally:
        if e is not None:e.dispose()


def race(database,jobs):
    ctx=mp.get_context('spawn')
    barrier=ctx.Barrier(len(jobs));output=ctx.Queue()
    processes=[ctx.Process(target=worker,args=(database,barrier,output,job)) for job in jobs]
    for p in processes:p.start()
    results=[]
    try:
        for _ in processes:results.append(output.get(timeout=35))
    finally:
        for p in processes:
            p.join(timeout=5)
            if p.is_alive():p.terminate();p.join()
        output.close();output.join_thread()
    assert len({r['pid'] for r in results})==len(jobs),results
    assert all(r['status']!=500 for r in results),results
    return results


def main():
    if not __debug__:raise SystemExit('Validation assertions require non-optimized Python')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True)
    args=parser.parse_args()
    e=make_engine(args.database)
    with e.connect() as c:
        users=dict(c.execute(text("SELECT username,id FROM sys_user WHERE username IN ('ENT_LOCAL_VERIFY_V1_employee_a','ENT_LOCAL_VERIFY_V1_employee_b','ENT_LOCAL_VERIFY_V1_student_a')")).all())
    a,b,s=(users['ENT_LOCAL_VERIFY_V1_'+key] for key in ('employee_a','employee_b','student_a'))
    common={'employee':a,'student':s}
    report={'database':args.database,'start_method':'spawn','workers_per_race':4,'rounds':[]}
    with e.begin() as c:
        for i in range(40):
            c.execute(insert(student_feedback_ticket).values(student_id=s,ticket_type='complaint',content='isolated scan contention',status='pending',priority='medium',assignee_id=a if i%2==0 else b,is_notified=0,create_time=now_naive(),update_time=now_naive()))
    report['parallel_scans']=race(args.database,[dict(common,operation='scan') for _ in range(4)])
    for iteration in range(3):
        token='parallel-'+uuid.uuid4().hex
        body={'student_id':s,'course_name':'并发验证课程','semester':'2026-2027-1','score':'85.50','exam_key':token,'submission_key':token}
        created=race(args.database,[dict(common,operation='create',body=body) for _ in range(4)])
        assert all(r['status']==200 for r in created),created
        assert len({r['data']['id'] for r in created})==1,created
        sid=created[0]['data']['id']
        corrected=race(args.database,[dict(common,operation='correct',score_id=sid,body={'student_id':s,'course_name':'并发验证课程','semester':'2026-2027-1','score':str(90+i),'expected_version':1,'correction_reason':'并发复核'}) for i in range(4)])
        assert sorted(r['status'] for r in corrected)==[200,409,409,409],corrected
        with e.connect() as c:
            grade=c.execute(select(student_score).where(student_score.c.id==sid)).mappings().one()
            history=c.execute(select(student_score_history.c.version).where(student_score_history.c.score_id==sid).order_by(student_score_history.c.version)).scalars().all()
            assert grade['version']==2 and history==[1,2],(grade,history)
        report['rounds'].append({'create':created,'correction':corrected,'score_id':sid,'history_versions':history})
    now=now_naive()
    with Session(e) as db:
        leave=StudentAdminService(student_id=s,service_type='leave',reason='isolated parallel approval',status='pending',approver_id=a,create_time=now,update_time=now)
        db.add(leave);db.commit();leave_id=leave.id
        scan_reminders(db)
    approved=race(args.database,[dict(common,operation='approve',leave_id=leave_id) for _ in range(4)])
    assert sorted(r['status'] for r in approved)==[200,409,409,409],approved
    with e.connect() as c:
        assert c.execute(select(todo_item.c.status).where(todo_item.c.related_type=='student_admin_service',todo_item.c.related_id==leave_id)).scalar_one()=='done'
    report['parallel_approval']=approved
    with e.begin() as c:
        ticket_id=c.execute(insert(student_feedback_ticket).values(student_id=s,ticket_type='complaint',content='isolated concurrent reassignment',status='pending',priority='medium',assignee_id=a,is_notified=0,create_time=now,update_time=now)).inserted_primary_key[0]
    with Session(e) as db:scan_reminders(db)
    report['reassignment_race']=race(args.database,[dict(common,operation='reassign',ticket_id=ticket_id,new_owner=b)]+[dict(common,operation='scan') for _ in range(3)])
    with Session(e) as db:scan_reminders(db)
    with e.connect() as c:
        row=c.execute(select(todo_item).where(todo_item.c.related_type=='student_feedback_ticket',todo_item.c.related_id==ticket_id)).mappings().one()
        assert row['assignee_id']==b and row['assignment_version']==2,row
        assert not c.execute(text('SELECT related_type,related_id,COUNT(*) n FROM todo_item WHERE related_type IS NOT NULL AND related_id IS NOT NULL GROUP BY related_type,related_id HAVING n>1')).first()
        assert not c.execute(text('SELECT dedup_key,COUNT(*) n FROM notification_log WHERE dedup_key IS NOT NULL GROUP BY dedup_key HAVING n>1')).first()
    report['invariants']={'one_score_per_exam':True,'one_winning_correction':True,'history_atomic':True,'one_winning_approval':True,'todo_reassignment_synchronized':True,'duplicate_source_todos':0,'duplicate_notification_keys':0}
    report['status']='passed'
    out=ROOT/'docs'/'回复Cursor'/'runs'/'ent-mysql-concurrency.json'
    out.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    print(json.dumps({'status':'passed','database':args.database,'process_operations':sum(len(r['create'])+len(r['correction']) for r in report['rounds'])+12,'invariants':report['invariants']},ensure_ascii=False))
    e.dispose()


if __name__=='__main__':
    try:
        main()
    except BaseException as exc:
        out=ROOT/'docs'/'回复Cursor'/'runs'/'ent-mysql-concurrency.json'
        out.write_text(json.dumps({'status':'failed','error_type':type(exc).__name__,'error':str(exc)},ensure_ascii=False,indent=2),encoding='utf-8')
        raise
