"""隔离 SQLite + ASGI 测试，不连接本地或云端 MySQL，不改变生产认证。"""
from datetime import datetime, date
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from app.core.config import Settings
from app.core.database import Base, get_db
from app.core.security import dependencies
from app.core.security import EmployeePrincipal, require_employee
from app.router_registry import register_routers
from app.modules.consultant.models import CrmLead, CrmFollowUp
from app.modules.employee_report.models import EmployeeDailyReport
from app.modules.student_admin.models import StudentAdminService, SysUser
from app.modules.student_admin.repository import StudentAdminRepository
from app.modules.consultant.errors import ConflictError

@pytest.fixture
def env(monkeypatch):
    # Keep blocked-mode assertions independent of local .env and process settings.
    settings = Settings(_env_file=None, employee_identity_mode="blocked")
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        now = datetime.now()
        for eid in (1, 2):
            db.add(CrmLead(id=eid, customer_name="同名客户", owner_employee_id=eid, status="new", create_time=now, update_time=now))
            db.add(EmployeeDailyReport(id=eid, employee_id=eid, report_date=date.today(), content=f"员工{eid}日报", status="submitted", create_time=now))
            db.add(SysUser(id=100+eid, real_name=f"学生{eid}", user_type="student", status="normal"))
        for lid, owner in ((1,1),(2,2),(3,None)):
            db.add(StudentAdminService(id=lid, student_id=101, service_type="leave", reason="测试", status="pending", approver_id=owner, create_time=now, update_time=now))
        db.add(CrmFollowUp(id=1, lead_id=1, employee_id=1, content="本人跟进", create_time=now))
        db.add(CrmFollowUp(id=2, lead_id=2, employee_id=2, content="他人跟进", create_time=now))
        db.commit()
        app = FastAPI()
        register_routers(app)
        app.dependency_overrides[require_employee] = lambda: EmployeePrincipal(employee_id=1, permissions=frozenset({"crm:read","crm:write","reports:read","leaves:read","leaves:approve"}))
        app.dependency_overrides[get_db] = lambda: db
        with TestClient(app) as client:
            yield client, db, app
    engine.dispose()

def test_reports_scope_and_no_side_effect(env):
    c, db, _ = env
    assert c.post("/api/v1/employee-reports", json={"employee_id":2,"content":"冒用"}).status_code == 403
    assert db.get(EmployeeDailyReport,2).content == "员工2日报"
    assert c.get("/api/v1/employee-reports?employee_id=2").status_code == 403
    rows = c.get("/api/v1/employee-reports").json()["data"]
    assert [x["employee_id"] for x in rows] == [1]
    r=c.post("/api/v1/employee-reports",json={"employee_id":1,"content":"本人更新"})
    assert r.status_code==200
    assert db.get(EmployeeDailyReport,1).content=="本人更新"

def test_leave_scope_and_repeat(env):
    c, db, _ = env
    assert [x["id"] for x in c.get("/api/v1/student-admin/leaves/pending").json()["data"]] == [1]
    assert c.get("/api/v1/student-admin/leaves/pending?approver_id=2").status_code==403
    payload={"approver_id":1,"decision":"approved"}
    for lid in (2,3):
        assert c.post(f"/api/v1/student-admin/leaves/{lid}/approve",json=payload).status_code==403
        assert db.get(StudentAdminService,lid).status=="pending"
    assert c.post("/api/v1/student-admin/leaves/999/approve",json=payload).status_code==404
    assert c.post("/api/v1/student-admin/leaves/1/approve",json=payload).status_code==200
    assert c.post("/api/v1/student-admin/leaves/1/approve",json=payload).status_code==409
    assert db.get(StudentAdminService,1).status=="approved"

def test_stale_approval_conditional_update(env):
    _,db,_=env
    repo=StudentAdminRepository(db)
    row=repo.get_leave(1)
    repo.approve(row,1,"approved",None)
    with pytest.raises(ConflictError):
        repo.approve(row,1,"rejected",None)
    db.expire_all()
    assert db.get(StudentAdminService,1).status=="approved"

@pytest.mark.parametrize("intent,params",[
    ("leads_by_status",{"status":"new","owner_employee_id":2}),
    ("daily_reports_recent",{"employee_id":2}),
    ("pending_leaves",{"approver_id":2}),
    ("lead_detail_by_name",{"customer_name":"同名客户","owner_employee_id":2}),
    ("leads_by_status",{"status":"new","sql":"select * from sys_user"}),
])
def test_nl_scope_override_rejected(env,intent,params):
    c,_,_=env
    assert c.post("/api/v1/ai/nl2sql/query",json={"intent":intent,"params":params}).status_code==403

@pytest.mark.parametrize("intent,params,key",[
    ("leads_by_status",{"status":"new"},"rows"),
    ("daily_reports_recent",{},"rows"),
    ("pending_leaves",{},"rows"),
    ("lead_follow_ups_by_name",{"customer_name":"同名客户"},"rows"),
])
def test_nl_queries_isolate_rows(env,intent,params,key):
    c,_,_=env
    r=c.post("/api/v1/ai/nl2sql/query",json={"intent":intent,"params":params})
    assert r.status_code==200
    rows=r.json()["data"]["result"][key]
    assert len(rows)==1
    assert rows[0].get("employee_id",rows[0].get("id"))==1

def test_name_query_and_command_scope(env):
    c,db,_=env
    r=c.post("/api/v1/ai/nl2sql/query",json={"intent":"lead_detail_by_name","params":{"customer_name":"同名客户"}})
    assert r.json()["data"]["result"]["lead"]["id"]==1
    command={"action":"update_lead_status_by_name","params":{"customer_name":"同名客户","status":"contacting"}}
    assert c.post("/api/v1/enterprise/commands",json=command).status_code==200
    assert db.get(CrmLead,1).status=="contacting"
    assert db.get(CrmLead,2).status=="new"
    command["params"]["status"]="new"
    assert c.post("/api/v1/enterprise/commands",json=command).status_code==409

def test_duplicate_names_are_not_chosen(env):
    c,db,_=env
    now=datetime.now()
    db.add(CrmLead(id=3,customer_name="同名客户",owner_employee_id=1,status="new",create_time=now,update_time=now))
    db.commit()
    assert c.post("/api/v1/ai/nl2sql/query",json={"intent":"lead_detail_by_name","params":{"customer_name":"同名客户"}}).status_code==409
    assert c.post("/api/v1/enterprise/commands",json={"action":"update_lead_status_by_name","params":{"customer_name":"同名客户","status":"lost","lost_reason":"测试"}}).status_code==409
    assert db.get(CrmLead,1).status==db.get(CrmLead,3).status=="new"

def test_leave_command_requires_decision_and_unique_target(env):
    c,db,_=env
    cmd={"action":"approve_leave_by_name","params":{"student_name":"学生1"}}
    assert c.post("/api/v1/enterprise/commands",json=cmd).status_code==400
    assert db.get(StudentAdminService,1).status=="pending"
    cmd["params"]["decision"]="rejected"
    assert c.post("/api/v1/enterprise/commands",json=cmd).status_code==200
    assert db.get(StudentAdminService,1).status=="rejected"
    assert db.get(StudentAdminService,2).status=="pending"

def test_production_auth_remains_blocked(env):
    c,_,app=env
    del app.dependency_overrides[require_employee]
    for path in ("/api/v1/employee-reports","/api/v1/student-admin/leaves/pending"):
        assert c.get(path).status_code==503
    assert c.post("/api/v1/ai/nl2sql/query",json={"intent":"pending_leaves"}).status_code==503
    assert c.post("/api/v1/enterprise/commands",json={"action":"approve_leave_by_name","params":{}}).status_code==503

@pytest.mark.parametrize("duplicate_student", [True, False])
def test_leave_ambiguity_rejected_without_writes(env, duplicate_student):
    c, db, _ = env
    if duplicate_student:
        db.add(SysUser(id=103,real_name="学生1",user_type="student",status="normal"))
    else:
        now=datetime.now()
        db.add(StudentAdminService(id=4,student_id=101,service_type="leave",reason="第二张",status="pending",approver_id=1,create_time=now,update_time=now))
    db.commit()
    r=c.post("/api/v1/enterprise/commands",json={"action":"approve_leave_by_name","params":{"student_name":"学生1","decision":"approved"}})
    assert r.status_code==409
    assert db.get(StudentAdminService,1).status=="pending"
    if not duplicate_student:
        assert db.get(StudentAdminService,4).status=="pending"

def test_bad_query_parameters_return_422(env):
    c,_,_=env
    for payload in (
        {"intent":"leads_by_status","params":{"status":"not_a_status"}},
        {"intent":"lead_detail_by_name","params":{}},
        {"intent":"pending_leaves","sql":"select 1"},
    ):
        assert c.post("/api/v1/ai/nl2sql/query",json=payload).status_code==422


def test_actor_fields_inferred_only_from_trusted_principal(env):
    c, db, app = env
    assert c.post("/api/v1/consultant/leads", json={"customer_name": "顾问不可建档"}).status_code == 403
    app.dependency_overrides[require_employee] = lambda: EmployeePrincipal(
        employee_id=1, permissions=frozenset({"crm:read", "crm:write", "reports:write", "leaves:approve"}),
        role_code="admin",
    )
    lead = c.post("/api/v1/consultant/leads",json={"customer_name":"可信身份验证"})
    assert lead.status_code == 200 and lead.json()["data"]["owner_employee_id"] == 1
    lid = lead.json()["data"]["id"]
    follow = c.post(f"/api/v1/consultant/leads/{lid}/follow-ups",json={"content":"只记录本人跟进"})
    assert follow.status_code == 200 and follow.json()["data"]["employee_id"] == 1
    report = c.post("/api/v1/employee-reports",json={"content":"本人日报"})
    assert report.status_code == 200 and report.json()["data"]["employee_id"] == 1
    approval = c.post("/api/v1/student-admin/leaves/1/approve",json={"decision":"approved"})
    assert approval.status_code == 200
    assert c.post("/api/v1/consultant/leads",json={"customer_name":"拒绝伪造","owner_employee_id":2}).status_code == 403
    del app.dependency_overrides[require_employee]
    assert c.post("/api/v1/consultant/leads",json={"customer_name":"不能匿名创建"}).status_code == 503

def test_assistant_business_reads_keep_current_employee_scope(env):
    client, db, app = env
    leaves = "/api/v1/student-admin/leaves/candidates"
    assert [row["id"] for row in client.get(leaves, params={"student_name": "学生1"}).json()["data"]["items"]] == [1]
    assert client.get(leaves, params={"student_name": "   "}).status_code == 422

    assert client.get("/api/v1/consultant/leads/2/follow-ups/count").status_code == 404
    now = datetime.now()
    db.add_all(CrmFollowUp(id=idx, lead_id=1, employee_id=1, content="跟进", create_time=now) for idx in range(3, 55))
    db.commit()
    assert client.get("/api/v1/consultant/leads/1/follow-ups/count").json()["data"]["total"] == 53
    result = client.post("/api/v1/ai/nl2sql/query", json={
        "intent": "lead_follow_ups_by_name", "params": {"customer_name": "同名客户"},
    }).json()["data"]["result"]
    assert result["total"] == 53
    assert len(result["rows"]) == 50
