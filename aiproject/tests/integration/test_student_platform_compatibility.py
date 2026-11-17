"""Merged student alert writer and upstream staff/report readers use one record.

All identities, notifications and rows are isolated SQLite fixtures.
"""
from sqlalchemy import text
from sqlalchemy.orm import Session
from tests.integration.test_ent_portal_routes import isolated_portal
from tests.integration.test_teacher_business import teacher_world, auth
from app.modules.student import assistant_chat


def test_student_disclosure_reaches_owned_teacher_and_manager_aggregate(teacher_world, monkeypatch):
    client, engine = teacher_world
    def no_legacy_model(*args, **kwargs):
        raise AssertionError('workspace must not invoke a second synchronous model')
    monkeypatch.setattr(assistant_chat, 'speak', no_legacy_model)
    with Session(engine) as db:
        result=assistant_chat._psych(db,21,'隔离联调：我想跳楼',[], 'Germany',generate_reply=False)
        assert result['intent']=='psych'
        row=db.execute(text('SELECT id,teacher_id,status,create_time FROM student_psych_alert WHERE student_id=21')).one()
        alert_id=row.id
        anchor=str(row.create_time)[:10]
        assert row.teacher_id==30 and row.status=='pending'
        assert db.execute(text("SELECT COUNT(*) FROM notification_log WHERE user_id=30 AND notification_type='psych_alert'")).scalar()==1
    listing=client.get('/api/v1/student-admin/psych-alerts?student_id=21',headers=auth('teacher'))
    assert listing.status_code==200,listing.text
    assert any(r['id']==alert_id for r in listing.json()['data'])
    denied=client.get('/api/v1/student-admin/psych-alerts?student_id=21',headers=auth('other'))
    assert denied.status_code==403
    week=client.get('/api/v1/reporting/wellbeing/week',params={'anchor':anchor},headers=auth('manager'))
    assert week.status_code==200,week.text
    assert any(r['status']=='pending' and r['risk_level']=='high' and r['count']==1 for r in week.json()['data']['items'])
    followed=client.put('/api/v1/student-admin/psych-alerts/'+str(alert_id),json={'status':'following','follow_record':'隔离联调：已由负责老师跟进'},headers=auth('teacher'))
    assert followed.status_code==200,followed.text
    week=client.get('/api/v1/reporting/wellbeing/week',params={'anchor':anchor},headers=auth('manager'))
    assert any(r['status']=='following' and r['count']==1 for r in week.json()['data']['items'])
