from datetime import date, datetime, timedelta

from sqlalchemy import Column, Integer, MetaData, Table, select, text, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.modules.auth.models import accounts
from app.modules.statistics import wellbeing, rule_signals, service as statistics_service
from app.modules.statistics.analysis_models import ReportRules
from app.modules.statistics.scheduled_repository import generated
from app.modules.statistics.wellbeing_models import WellbeingConsent, WellbeingCheckin
from tests.integration.test_teacher_business import teacher_world, auth
from tests.integration.test_ent_portal_routes import isolated_portal


def test_rule_configuration_and_self_assessment_are_opt_in_and_idempotent(teacher_world, monkeypatch):
    client, engine = teacher_world
    endpoint = "/api/v1/reporting/rules"
    response = client.get(endpoint, headers=auth("admin"))
    assert response.status_code == 200
    assert response.json()["data"]["settings"]["psych_negative_days"] is None
    assert client.put(endpoint, headers=auth("manager"), json={
        "expected_version": 0, "settings": {"psych_negative_days": 3, "psych_alert_level": "medium"}
    }).status_code == 403
    assert client.put(endpoint, headers=auth("admin"), json={
        "expected_version": 0, "settings": {"psych_negative_days": 3}
    }).status_code == 422
    body = {"expected_version": 0, "settings": {"psych_negative_days": 3, "psych_alert_level": "medium"}}
    assert client.put(endpoint, headers=auth("admin"), json=body).status_code == 200
    assert client.put(endpoint, headers=auth("admin"), json=body).status_code == 409
    now = datetime(2026, 11, 17, 10)
    monkeypatch.setattr(wellbeing, "beijing_now", lambda: now)
    with Session(engine) as db:
        db.add(WellbeingConsent(student_id=21, granted=True, version="v1", updated_at=now))
        for day in (date(2026,11,15), date(2026,11,16)):
            db.add(WellbeingCheckin(student_id=21, day=day, emotion="poor", stress="light", updated_at=now))
        db.commit()
        wellbeing.save_checkin(db, 21, wellbeing.CheckinInput(emotion="poor", stress="high"))
        wellbeing.save_checkin(db, 21, wellbeing.CheckinInput(emotion="poor", stress="high"))
        rows = db.execute(text("SELECT student_id,teacher_id,risk_level,status FROM student_psych_alert")).all()
        assert rows == [(21,30,"medium","pending")]
        assert db.scalar(text("SELECT COUNT(*) FROM report_rule_signal")) == 1
        assert db.scalar(text("SELECT COUNT(*) FROM notification_log WHERE notification_type='psych_alert'")) == 1


def test_shared_psych_archives_follow_current_class_enrollment(teacher_world):
    client, engine = teacher_world
    Table("report_generation", MetaData(), Column("id", Integer, primary_key=True),
          *(Column(col.name, col.type) for col in generated.c if col.name != "id")).create(engine)
    with Session(engine) as db:
        db.execute(generated.insert().values(id=1, report_type="psych_weekly", report_title="测试心理周报",
            generated_by=30,status="completed",period_start=date(2026,11,9),period_end=date(2026,11,15),
            create_time=datetime(2026,11,16),report_content={"scope_version":1,"student_ids":[21],
            "statistics":{"items":[]}}))
        db.commit()
    endpoint="/api/v1/reporting/archive"
    assert client.get(endpoint, headers=auth("other")).json()["data"] == []
    assert client.get(endpoint, headers=auth("other"),params={"shared":True}).json()["data"] == []
    assert client.get(endpoint, headers=auth("manager"),params={"shared":True}).json()["data"][0]["id"] == 1
    with Session(engine) as db:
        db.execute(text("UPDATE student_class_enrollment SET class_id=2 WHERE student_id=21"))
        db.commit()
    assert client.get(endpoint, headers=auth("other"),params={"shared":True}).json()["data"][0]["id"] == 1
    assert client.get(endpoint, headers=auth("teacher"),params={"shared":True}).json()["data"] == []
    assert client.get(endpoint+"/1/pdf",headers=auth("other"),params={"shared":True}).status_code == 200
    assert client.get(endpoint+"/1/pdf",headers=auth("teacher"),params={"shared":True}).status_code == 403


def test_complaint_escalation_and_repeat_notifications_are_deduplicated(teacher_world, monkeypatch):
    _, engine = teacher_world
    monkeypatch.setattr(statistics_service,"get_settings",lambda:Settings(_env_file=None,employee_identity_mode="trusted_jwt"))
    now=datetime(2026,11,17,10)
    monkeypatch.setattr(rule_signals,"beijing_now",lambda:now)
    with Session(engine) as db:
        db.execute(update(accounts).where(accounts.c.id.in_((11,30))).values(department="A"))
        db.add(ReportRules(id=1,version=1,settings={"complaint_overdue_days":3,"complaint_escalate_days":5,
            "reminder_repeat_days":2},updated_by=10,updated_at=now))
        db.execute(text("INSERT INTO student_feedback_ticket "
            "(id,student_id,ticket_type,content,status,priority,assignee_id,is_notified,create_time,update_time) "
            "VALUES (1,21,'complaint','测试','pending','medium',30,0,:stamp,:stamp)"),
            {"stamp":now-timedelta(days=6)})
        db.commit()
        assert rule_signals.scan_operational_signals(db) == 2
        assert rule_signals.scan_operational_signals(db) == 0
        recipients=set(db.scalars(text("SELECT user_id FROM notification_log WHERE notification_type='complaint_overdue'")))
        assert recipients == {11,30}
        monkeypatch.setattr(rule_signals,"beijing_now",lambda:now+timedelta(days=2))
        assert rule_signals.scan_operational_signals(db) == 2


def test_scheduled_ai_is_opt_in_and_does_not_duplicate_a_run(isolated_portal, monkeypatch):
    from app.modules.auth.repository import AuthRepository
    from app.modules.statistics import scheduled, formal_dify
    from app.modules.statistics.analysis_models import ReportScheduleOptions
    from app.modules.statistics.schemas import FormalReportSections
    _, engine = isolated_portal("trusted_jwt")
    with Session(engine) as db:
        db.execute(text("CREATE TABLE report_schedule (id INTEGER PRIMARY KEY, report_type TEXT, schedule_cron TEXT, "
                        "recipients JSON, enabled INTEGER, last_run_time DATETIME, create_time DATETIME, update_time DATETIME)"))
        Table("report_generation", MetaData(), Column("id", Integer, primary_key=True),
              *(Column(col.name,col.type) for col in generated.c if col.name!="id")).create(engine)
        db.execute(text("INSERT INTO report_schedule (id,report_type,schedule_cron,recipients,enabled,create_time) "
                        "VALUES (1,'daily_summary','0 9 * * *','[1]',1,'2026-11-01 09:00:00')"))
        db.add(ReportScheduleOptions(schedule_id=1,include_ai=True))
        db.commit()
    now=datetime(2026,11,17,10)
    monkeypatch.setattr(scheduled,"_now",lambda:now)
    monkeypatch.setattr(AuthRepository,"account",lambda *args,**kwargs:{
        "status":"normal","user_type":"employee","role_status":1,"role_id":1,"role_code":"admin"})
    monkeypatch.setattr(AuthRepository,"permissions",lambda *args:{"reports:summary:read","reports:formal:generate"})
    monkeypatch.setattr(AuthRepository,"scope",lambda *args:set())
    monkeypatch.setattr(scheduled,"_allowed_kinds",lambda *args,**kwargs:("daily_summary",))
    monkeypatch.setattr(scheduled,"_snapshot",lambda *args,**kwargs:{
        "period_start":date(2026,11,16),"period_end":date(2026,11,16),"department":None,
        "submitted_employee_days":1,"days":[{"report_date":date(2026,11,16),"submitted_employees":1}]})
    monkeypatch.setattr(scheduled.service,"_report_payload",lambda *args:("{}",{1}))
    calls=[]
    def generate(kind,payload):
        calls.append(kind)
        return FormalReportSections(work_summary="工作总结",key_progress_summary="进展",
                                    risk_summary="风险",next_work_suggestions="计划")
    monkeypatch.setattr(formal_dify,"generate_summary",generate)
    with Session(engine) as db:
        assert scheduled.scan_reports(db)==1
        assert scheduled.scan_reports(db)==0
        assert calls==["daily"]
        content=db.scalar(select(generated.c.report_content))
        assert content["format"]=="formal"
        assert content["statistics"]["sections"]["work_summary"]=="工作总结"


def test_shared_employee_archives_require_both_owner_and_snapshot_scope(isolated_portal, monkeypatch):
    from fastapi.testclient import TestClient
    from app.core.security import EmployeePrincipal
    from app.modules.auth import service as auth_service
    from app.modules.student_admin.models import SysUser
    app, engine = isolated_portal("trusted_jwt")
    monkeypatch.setattr(statistics_service,"get_settings",lambda:Settings(_env_file=None,employee_identity_mode="trusted_jwt"))
    monkeypatch.setattr(auth_service.AuthService,"authenticate",lambda *args:
        EmployeePrincipal(10,frozenset({"reports:summary:read"}),role_code="manager"))
    Table("report_generation", MetaData(), Column("id",Integer,primary_key=True),
          *(Column(col.name,col.type) for col in generated.c if col.name!="id")).create(engine)
    with Session(engine) as db:
        db.add_all([SysUser(id=uid,real_name=str(uid),user_type="employee",department=department)
                    for uid,department in ((10,"A"),(11,"A"),(12,"B"))])
        for rid,owner,department in ((1,11,"A"),(2,12,"B"),(3,11,"B")):
            db.execute(generated.insert().values(id=rid,report_type="daily_summary",report_title="测试汇总",
                generated_by=owner,status="completed",period_start=date(2026,11,16),period_end=date(2026,11,16),
                create_time=datetime(2026,11,17),report_content={"scope_version":1,"department":department,
                    "department_members":None,"statistics":{"days":[],"submitted_employee_days":0}}))
        db.commit()
    endpoint="/api/v1/reporting/archive"
    with TestClient(app) as client:
        headers=auth("manager")
        assert client.get(endpoint,headers=headers).json()["data"] == []
        rows=client.get(endpoint,headers=headers,params={"shared":True}).json()["data"]
        assert [row["id"] for row in rows] == [1]
        assert client.get(endpoint+"/1/pdf",headers=headers,params={"shared":True}).status_code==200
        assert client.get(endpoint+"/2/pdf",headers=headers,params={"shared":True}).status_code==404
        assert client.get(endpoint+"/3/pdf",headers=headers,params={"shared":True}).status_code==403


def test_project_health_uses_configured_weights_and_includes_shared_deadlines(teacher_world, monkeypatch):
    from app.modules.statistics import analysis, periods
    from app.modules.student.models import ApplicationProgress, AcademicDeadline
    from app.core.security import EmployeePrincipal
    _, engine = teacher_world
    now=datetime(2026,11,17,10)
    monkeypatch.setattr(periods,"beijing_now",lambda:now)
    monkeypatch.setattr(statistics_service,"current_report_members",lambda *args:{30})
    principal=EmployeePrincipal(11,frozenset({"reports:summary:read"}),role_code="manager")
    with Session(engine) as db:
        before=analysis.project_health(db,principal)
        assert [row["project_id"] for row in before["items"]]==[1]
        assert before["items"][0]["score"] is None
        db.add(ReportRules(id=1,version=1,settings={"project_complaint_weight":0.5,
            "project_application_weight":0.25,"project_deadline_weight":0.25},updated_by=10,updated_at=now))
        db.execute(text("INSERT INTO student_feedback_ticket "
            "(id,student_id,ticket_type,content,status,priority,assignee_id,is_notified,create_time,update_time) "
            "VALUES (1,21,'complaint','测试','pending','medium',30,0,:stamp,:stamp)"),{"stamp":now})
        db.add(ApplicationProgress(student_id=21,target_school="测试院校",stage="document_prep",
            deadline=now.date()-timedelta(days=1),handler_id=30,create_time=now,update_time=now))
        db.add(AcademicDeadline(student_id=None,deadline_type="exam",title="共享考试",study_stage="preparatory",
            deadline=now-timedelta(days=1),status="pending",create_time=now,update_time=now))
        db.commit()
        row=analysis.project_health(db,principal)["items"][0]
        assert row["project_name"]=="预科项目"
        assert row["students"]==row["open_complaints"]==row["overdue_applications"]==row["overdue_deadlines"]==1
        assert row["score"]==0
