from datetime import datetime, timedelta
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, insert, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.core.config import Settings
from app.core.database import Base, get_db
from app.core.security import dependencies
from app.core.security import EmployeePrincipal, require_employee
from app.router_registry import register_routers
from app.modules.student_admin.models import SysUser, StudentAdminService
from app.modules.organization.models import sys_organization as org
from app.modules.onboarding.models import onboarding_guide as guide
from app.modules.score.models import student_score as scores
from app.modules.feedback.models import student_feedback_ticket as tickets
from app.modules.todo.models import todo_item as todos, notification_log as notices
from app.modules.todo.reminders import scan_reminders

@pytest.fixture
def env(monkeypatch):
    # Keep blocked-mode assertions independent of local .env and process settings.
    settings = Settings(_env_file=None, employee_identity_mode="blocked")
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    engine=create_engine("sqlite://",connect_args={"check_same_thread":False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        now=datetime.now()
        db.add(SysUser(id=101,real_name="学生",user_type="student",status="normal"))
        db.add(SysUser(id=1,real_name="老师",user_type="employee",status="normal"))
        for rid in (1,2):
            db.execute(insert(org).values(id=rid,org_name="教学部",org_level=2,sort_order=0,status=1 if rid==1 else 0,create_time=now,update_time=now))
            db.execute(insert(tickets).values(id=rid,student_id=101,ticket_type="complaint",content="投诉",status="pending",priority="medium",assignee_id=rid,is_notified=0,create_time=now,update_time=now))
        db.commit()
        app=FastAPI();register_routers(app)
        app.dependency_overrides[get_db]=lambda:db
        app.dependency_overrides[require_employee]=lambda:EmployeePrincipal(1)
        with TestClient(app) as c:yield c,db,app
    engine.dispose()

def grant(app):
    app.dependency_overrides[require_employee]=lambda:EmployeePrincipal(1,frozenset({"scores:read","scores:write","guides:write"}),frozenset({101}))

def test_directory_hides_disabled_and_students(env):
    c,db,app=env
    assert len(c.get("/api/v1/enterprise/organizations").json()["data"])==1
    assert c.get("/api/v1/enterprise/colleagues/1/contact").status_code==403
    assert c.get("/api/v1/enterprise/organizations/colleagues?name=学生").json()["data"]==[]
    assert c.get("/api/v1/enterprise/organizations/colleagues?name=老师").json()["data"]==[{"id":1,"real_name":"老师","department":None}]

def test_guides_require_editor_and_search(env):
    c,db,app=env
    body={"title":"入职","category":"流程","content":"领取电脑"}
    assert c.post("/api/v1/enterprise/onboarding-guides",json=body).status_code==403
    grant(app)
    assert c.post("/api/v1/enterprise/onboarding-guides",json=body).status_code==200
    assert len(c.get("/api/v1/enterprise/onboarding-guides?keyword=电脑").json()["data"])==1
    assert c.get("/api/v1/enterprise/onboarding-guides?keyword=不存在").json()["data"]==[]

def test_score_permissions_scope_validation_and_correction(env):
    c,db,app=env
    body={"student_id":101,"course_name":"数学","score":"85.50","semester":"2026-1"}
    assert c.post("/api/v1/enterprise/scores",json=body).status_code==403
    grant(app)
    response=c.post("/api/v1/enterprise/scores",json=body)
    assert response.status_code==200
    sid=response.json()["data"]["id"]
    assert c.get("/api/v1/enterprise/scores?student_id=102").status_code==403
    assert len(c.get("/api/v1/enterprise/scores?student_id=101").json()["data"])==1
    body["score"]="90.25"
    assert c.put(f"/api/v1/enterprise/scores/{sid}",json=body).status_code==200
    assert str(db.execute(select(scores.c.score)).scalar_one())=="90.25"
    body["score"]="-1"
    assert c.post("/api/v1/enterprise/scores",json=body).status_code==422
    body["score"]="1.123"
    assert c.post("/api/v1/enterprise/scores",json=body).status_code==422

def test_ticket_ownership_transitions_and_notification_truth(env):
    c,db,_=env
    body={"expected_status":"pending","status":"processing"}
    assert c.patch("/api/v1/enterprise/tickets/2",json=body).status_code==403
    assert db.execute(select(tickets.c.status).where(tickets.c.id==2)).scalar_one()=="pending"
    assert len(c.get("/api/v1/enterprise/tickets").json()["data"])==1
    assert c.patch("/api/v1/enterprise/tickets/1",json=body).status_code==200
    assert c.patch("/api/v1/enterprise/tickets/1",json=body).status_code==409
    body={"expected_status":"processing","status":"resolved"}
    assert c.patch("/api/v1/enterprise/tickets/1",json=body).status_code==422
    body["solution"]="已处理并核实"
    assert c.patch("/api/v1/enterprise/tickets/1",json=body).json()["data"]["is_notified"]==0
    assert c.patch("/api/v1/enterprise/tickets/1",json={"expected_status":"resolved","status":"closed"}).status_code==200

def test_todo_due_notification_dedup_and_terminal_state(env):
    c,db,_=env
    now=datetime.now()
    response=c.post("/api/v1/enterprise/todos",json={"title":"联系客户","due_time":(now-timedelta(minutes=1)).isoformat()})
    assert response.status_code==200
    tid=response.json()["data"]["id"]
    assert len(c.get("/api/v1/enterprise/todos?due_only=true").json()["data"])==1
    first=scan_reminders(db)
    assert first["todos_created"]==2
    assert first["system_notifications_created"]==3
    assert scan_reminders(db)=={"todos_created":0,"system_notifications_created":0}
    # 员工只看本人通知，另一员工工单通知不能泄露。
    assert len(c.get("/api/v1/enterprise/notifications").json()["data"])==2
    body={"expected_status":"pending","status":"done"}
    assert c.patch(f"/api/v1/enterprise/todos/{tid}",json=body).status_code==200
    assert c.patch(f"/api/v1/enterprise/todos/{tid}",json=body).status_code==409
    other=db.execute(select(todos.c.id).where(todos.c.assignee_id==2)).scalar_one()
    assert c.patch(f"/api/v1/enterprise/todos/{other}",json=body).status_code==403

def test_all_new_routes_stay_blocked_without_auth(env):
    c,_,app=env
    del app.dependency_overrides[require_employee]
    for path in ("organizations","onboarding-guides","scores?student_id=101","tickets","todos","notifications"):
        assert c.get("/api/v1/enterprise/"+path).status_code==503


@pytest.mark.parametrize("student_state", ["disabled", "missing"])
def test_score_correction_rejects_inactive_student_without_changes(env, student_state):
    c, db, app = env
    grant(app)
    body = {"student_id":101,"course_name":"数学","score":"85.50"}
    sid = c.post("/api/v1/enterprise/scores", json=body).json()["data"]["id"]
    student = db.get(SysUser, 101)
    if student_state == "missing":
        db.delete(student)
    else:
        student.status = "disabled"
    db.commit()
    body["score"] = "90.00"
    response = c.put(f"/api/v1/enterprise/scores/{sid}", json=body)
    assert response.status_code == 422
    assert str(db.execute(select(scores.c.score).where(scores.c.id == sid)).scalar_one()) == "85.50"


def test_reminder_batches_progress_without_duplicates_or_other_employees(env):
    c, db, app = env
    now = datetime.now()
    for index in range(201):
        db.add(StudentAdminService(id=10000 + index, student_id=101, service_type="leave", reason="分批扫描验证", status="pending", approver_id=1, create_time=now, update_time=now))
    db.commit()
    assert scan_reminders(db, employee_ids=frozenset()) == {"todos_created": 0, "system_notifications_created": 0}
    first = scan_reminders(db, employee_ids=frozenset({1}))
    second = scan_reminders(db, employee_ids=frozenset({1}))
    assert first["todos_created"] == 201  # 200 leaves and one assigned ticket.
    assert second["todos_created"] == 1  # The next batch is valid progress.
    rows = db.execute(select(todos.c.related_id).where(todos.c.related_type == "student_admin_service")).scalars().all()
    assert len(rows) == len(set(rows)) == 201
    assert db.execute(select(todos.c.id).where(todos.c.assignee_id == 2)).first() is None
    assert scan_reminders(db, employee_ids=frozenset({1})) == {"todos_created": 0, "system_notifications_created": 0}


def test_score_idempotency_exam_identity_versions_and_history(env):
    c, db, app = env
    grant(app)
    body = {"student_id":101,"course_name":"数学","score":"85.50","semester":"2026-1","exam_key":"midterm","submission_key":"submit-1"}
    first = c.post("/api/v1/enterprise/scores", json=body).json()["data"]
    sid = first["id"]
    second = c.post("/api/v1/enterprise/scores", json=body).json()["data"]
    assert second["id"] == sid and second["replayed"] is True
    assert len(c.get(f"/api/v1/enterprise/scores/{sid}/history").json()["data"]) == 1
    assert c.post("/api/v1/enterprise/scores", json={**body,"score":"88.00"}).status_code == 409
    assert c.post("/api/v1/enterprise/scores", json={**body,"exam_key":"final"}).status_code == 409
    another = c.post("/api/v1/enterprise/scores", json={**body,"exam_key":"final","submission_key":"submit-2"})
    assert another.status_code == 200 and another.json()["data"]["id"] != sid
    correction = {"student_id":101,"course_name":"数学","score":"90.00","semester":"2026-1","expected_version":1,"correction_reason":"复核试卷"}
    assert c.put(f"/api/v1/enterprise/scores/{sid}", json=correction).json()["data"]["version"] == 2
    assert c.put(f"/api/v1/enterprise/scores/{sid}", json=correction).status_code == 409
    history = c.get(f"/api/v1/enterprise/scores/{sid}/history").json()["data"]
    assert [r["version"] for r in history] == [2,1]
    assert history[0]["before_data"]["score"] == "85.50"
    assert history[0]["after_data"]["score"] == "90.00"
    # Retry the original submission after correction must not revert the grade.
    assert c.post("/api/v1/enterprise/scores", json=body).json()["data"]["id"] == sid
    assert str(db.execute(select(scores.c.score).where(scores.c.id==sid)).scalar_one()) == "90.00"
    app.dependency_overrides[require_employee] = lambda: EmployeePrincipal(2, frozenset({"scores:read"}), frozenset())
    assert c.get(f"/api/v1/enterprise/scores/{sid}/history").status_code == 403


def test_score_history_failure_rolls_back_grade(env, monkeypatch):
    from app.modules.score.repository import ScoreRepository
    c, db, app = env
    grant(app)
    body = {"student_id":101,"course_name":"数学","score":"85.50"}
    sid = c.post("/api/v1/enterprise/scores", json=body).json()["data"]["id"]
    def broken_history(self, values):
        raise RuntimeError("simulated history failure")
    monkeypatch.setattr(ScoreRepository, "add_history", broken_history)
    with pytest.raises(RuntimeError, match="history failure"):
        c.put(f"/api/v1/enterprise/scores/{sid}", json={**body,"score":"90.00","expected_version":1})
    row = db.execute(select(scores).where(scores.c.id==sid)).mappings().one()
    assert str(row["score"]) == "85.50" and row["version"] == 1


def test_source_todo_reassignment_completion_reopening_and_unassignment(env):
    from sqlalchemy import update
    c, db, app = env
    scan_reminders(db)
    tid = db.execute(select(todos.c.id).where(todos.c.related_type=="student_feedback_ticket", todos.c.related_id==1)).scalar_one()
    db.execute(update(tickets).where(tickets.c.id==1).values(assignee_id=2));db.commit()
    scan_reminders(db, employee_ids=frozenset({1}))
    row = db.execute(select(todos).where(todos.c.id==tid)).mappings().one()
    assert row["assignee_id"] == 2 and row["assignment_version"] == 2
    assert c.patch(f"/api/v1/enterprise/todos/{tid}",json={"expected_status":"pending","status":"done"}).status_code == 403
    scan_reminders(db)
    db.execute(update(tickets).where(tickets.c.id==1).values(assignee_id=1));db.commit()
    scan_reminders(db)
    row = db.execute(select(todos).where(todos.c.id==tid)).mappings().one()
    assert row["assignment_version"] == 3 and row["assignee_id"] == 1
    assert c.patch("/api/v1/enterprise/tickets/1",json={"expected_status":"pending","status":"processing"}).status_code == 200
    assert c.patch("/api/v1/enterprise/tickets/1",json={"expected_status":"processing","status":"resolved","solution":"已复核"}).status_code == 200
    assert db.execute(select(todos.c.status).where(todos.c.id==tid)).scalar_one() == "done"
    db.execute(update(tickets).where(tickets.c.id==1).values(status="pending"));db.commit()
    scan_reminders(db)
    assert db.execute(select(todos.c.assignment_version).where(todos.c.id==tid)).scalar_one() == 4
    db.execute(update(tickets).where(tickets.c.id==1).values(assignee_id=None));db.commit()
    scan_reminders(db)
    assert db.execute(select(todos.c.status).where(todos.c.id==tid)).scalar_one() == "cancelled"
    db.execute(update(tickets).where(tickets.c.id==1).values(assignee_id=1));db.commit()
    scan_reminders(db)
    assert db.execute(select(todos.c.assignment_version).where(todos.c.id==tid)).scalar_one() == 5
    assert c.patch(f"/api/v1/enterprise/todos/{tid}",json={"expected_status":"pending","status":"done"}).status_code == 200
    scan_reminders(db)
    assert db.execute(select(todos.c.status).where(todos.c.id==tid)).scalar_one() == "done"
    keys = db.execute(select(notices.c.dedup_key).where(notices.c.related_id==tid,notices.c.related_type=="todo_item")).scalars().all()
    assert len(keys) == len(set(keys)) == 5


def test_leave_approval_and_deleted_source_synchronize_todo(env):
    c, db, app = env
    now=datetime.now()
    db.add(StudentAdminService(id=500,student_id=101,service_type="leave",reason="测试",status="pending",approver_id=1,create_time=now,update_time=now));db.commit()
    scan_reminders(db)
    tid=db.execute(select(todos.c.id).where(todos.c.related_type=="student_admin_service",todos.c.related_id==500)).scalar_one()
    assert c.post("/api/v1/student-admin/leaves/500/approve",json={"approver_id":1,"decision":"approved"}).status_code == 200
    assert db.execute(select(todos.c.status).where(todos.c.id==tid)).scalar_one() == "done"
    ticket_todo=db.execute(select(todos.c.id).where(todos.c.related_type=="student_feedback_ticket",todos.c.related_id==1)).scalar_one()
    db.execute(tickets.delete().where(tickets.c.id==1));db.commit()
    scan_reminders(db)
    assert db.execute(select(todos.c.status).where(todos.c.id==ticket_todo)).scalar_one() == "cancelled"


@pytest.mark.parametrize("source", ["ticket", "leave"])
def test_source_update_rolls_back_if_todo_sync_fails(env, monkeypatch, source):
    from app.modules.todo import synchronization
    c, db, app = env
    now = datetime.now()
    if source == "leave":
        db.add(StudentAdminService(id=600,student_id=101,service_type="leave",reason="原子性",status="pending",approver_id=1,create_time=now,update_time=now));db.commit()
    def broken(*args, **kwargs):
        raise RuntimeError("simulated synchronization failure")
    monkeypatch.setattr(synchronization, "synchronize_source", broken)
    with pytest.raises(RuntimeError, match="synchronization failure"):
        if source == "leave":
            c.post("/api/v1/student-admin/leaves/600/approve",json={"approver_id":1,"decision":"approved"})
        else:
            c.patch("/api/v1/enterprise/tickets/1",json={"expected_status":"pending","status":"processing"})
    if source == "leave":
        db.expire_all()
        assert db.get(StudentAdminService,600).status == "pending"
    else:
        assert db.execute(select(tickets.c.status).where(tickets.c.id==1)).scalar_one() == "pending"


def test_scanner_notifies_new_assignment_even_if_sync_crosses_second(env,monkeypatch):
    """The notification cutoff must be captured AFTER source timestamps advance."""
    from sqlalchemy import update
    from app.modules.todo import reminder_repository,synchronization
    _,db,_=env
    clock={'now':datetime(2030,1,1,12,0,0)}
    def sync_time():
        clock['now']+=timedelta(seconds=1)
        return clock['now']
    monkeypatch.setattr(synchronization,'now_naive',sync_time)
    monkeypatch.setattr(reminder_repository,'now_naive',lambda:clock['now'])
    scan_reminders(db)
    tid=db.execute(select(todos.c.id).where(todos.c.related_type=='student_feedback_ticket',todos.c.related_id==1)).scalar_one()
    keys=lambda:list(db.execute(select(notices.c.dedup_key).where(notices.c.related_type=='todo_item',notices.c.related_id==tid)).scalars())
    assert keys()==[f'todo:{tid}:1:1']
    db.execute(update(tickets).where(tickets.c.id==1).values(assignee_id=2));db.commit()
    scan_reminders(db)
    assert set(keys())=={f'todo:{tid}:1:1',f'todo:{tid}:2:2'}
    assert scan_reminders(db)=={'todos_created':0,'system_notifications_created':0}
