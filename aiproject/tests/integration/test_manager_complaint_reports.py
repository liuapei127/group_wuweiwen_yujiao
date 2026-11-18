from datetime import datetime
import json

from fastapi.testclient import TestClient
from sqlalchemy import text,Table,MetaData,Column,Integer
from sqlalchemy.orm import Session

from app.core.security import EmployeePrincipal
from app.modules.auth import service as auth_service
from app.modules.auth.models import audit_log
from app.modules.consultant.models import CrmLead
from app.modules.feedback.models import student_feedback_ticket
from app.modules.statistics import scheduled
from app.modules.student_admin.models import SysUser
from tests.integration.test_ent_portal_routes import isolated_portal


def test_manager_complaint_report_stays_in_department_even_with_all_ticket_read(isolated_portal,monkeypatch):
    app,engine=isolated_portal('trusted_jwt')
    from app.modules.statistics.scheduled_repository import generated
    Table('report_generation',MetaData(),Column('id',Integer,primary_key=True),
          *(Column(col.name,col.type) for col in generated.c if col.name!='id')).create(engine)
    permissions={'reports:operations:read','tickets:read'}
    manager=lambda:EmployeePrincipal(10,frozenset(permissions),role_code='manager')
    monkeypatch.setattr(auth_service.AuthService,'authenticate',lambda self,token:manager())
    day=datetime(2026,11,10,8)
    with Session(engine) as db:
        db.execute(text('CREATE TABLE report_status_history_start (id INTEGER PRIMARY KEY, start_day DATE)'))
        db.add_all(SysUser(id=i,real_name=str(i),department=dept,user_type='employee')
                   for i,dept in [(10,'A'),(11,'A'),(12,'B')])
        db.add_all(CrmLead(id=i,customer_name=str(i),owner_employee_id=owner,status='new',create_time=day,update_time=day)
                   for i,owner in [(1,11),(2,12)])
        db.execute(student_feedback_ticket.insert(),[
            dict(id=i,student_id=21,assignee_id=owner,ticket_type=kind,status='pending',category='learning',
                 title=str(i),content='测试',priority='medium',is_notified=0,create_time=day,update_time=day)
            for i,owner,kind in [(1,11,'complaint'),(2,12,'complaint'),(3,None,'complaint'),(4,11,'suggestion')]])
        db.execute(audit_log.insert(),[dict(actor_id=11,target=str(i),action='ticket_processed',
            details=json.dumps({'status':'processing'}),create_time=datetime(2026,11,10,2)) for i in (1,2,3)])
        db.commit()
    headers={'Authorization':'Bearer manager'}
    root='/api/v1/reporting'
    params={'start':'2026-11-01','end':'2026-11-18'}
    try:
        with TestClient(app) as client:
            report=client.get(root+'/board/complaints',headers=headers,params=params)
            assert report.status_code==200,report.text
            assert report.json()['data']['department']=='A'
            assert report.json()['data']['complaints_by_status']=={'pending':1}
            for extra in [{'metric':'new'},{'metric':'category','bucket':'learning'},{'metric':'status','bucket':'pending'}]:
                details=client.get(root+'/board/complaints',headers=headers,params={**params,**extra}).json()['data']
                assert {r['id'] for r in details['items']}=={1}
            analysis=client.get(root+'/board/complaints/analysis',headers=headers,params=params).json()['data']
            assert analysis['first_response']['samples']==1
            customers=client.get(root+'/board/customers',headers=headers,params={**params,'metric':'new'}).json()['data']
            assert customers['department']=='A' and [r['id'] for r in customers['items']]==[1]
            archive=client.post(root+'/board/complaints/archive',headers=headers,json=params)
            assert archive.status_code==201,archive.text
            archive_id=archive.json()['data']['archive_id']
            with Session(engine) as db:
                saved=scheduled.archived_report(db,manager(),archive_id)
                assert saved['report_content']['complaints_by_status']=={'pending':1}
                global_id=db.execute(generated.insert().values(
                    report_type='complaint_weekly',report_title='旧全公司报告',generated_by=10,status='completed',
                    period_start=day.date(),period_end=day.date(),create_time=day,
                    report_content={'scope_version':1,'department':None,'department_members':None,
                                    'statistics':{'complaints_by_status':{'pending':3}}})).lastrowid
                db.commit()
            permissions.remove('tickets:read')
            limited=client.get(root+'/board/complaints',headers=headers,params=params).json()['data']
            assert limited['department']=='A' and limited['complaints_by_status']=={'pending':1}
            archives=client.get(root+'/archive',headers=headers,params={'kind':'complaint_weekly'}).json()['data']
            indexed={row['id']:row for row in archives}
            assert indexed[archive_id]['report_content']['complaints_by_status']=={'pending':1}
            assert indexed[global_id]=={'id':global_id,'unavailable':True}
            assert client.get(f'{root}/archive/{global_id}/pdf',headers=headers).status_code==403
            # An empty department returns a valid empty report instead of falling back to company data.
            with Session(engine) as db:
                db.get(SysUser,11).department='B'
                db.commit()
            empty=client.get(root+'/board/complaints',headers=headers,params={**params,'metric':'new'}).json()['data']
            assert empty['department']=='A' and empty['complaints_by_status']=={} and empty['items']==[]
            assert all(count==0 for count in empty['backlog'].values())
    finally:
        engine.dispose()
