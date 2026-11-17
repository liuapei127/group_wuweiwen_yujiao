import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.security import EmployeePrincipal
from app.core.security.credentials import hash_password, utc_now
from app.modules.auth import service as auth_service
from app.modules.auth.models import audit_log, role_permissions, roles
from app.modules.student_admin.models import SysUser
from app.modules.todo.models import todo_item
from app.modules.visitor.models import VisitorAccount, WebsiteStudentAccess
from app.modules.visitor import repository as visitor_repository
from app.modules.visitor import router as visitor_router
from tests.integration.test_ent_portal_routes import isolated_portal


def test_website_account_keeps_credentials_and_routes_by_authorized_student_access(isolated_portal, monkeypatch):
    app, engine = isolated_portal("trusted_jwt")
    actors = {
        "operator": EmployeePrincipal(10, frozenset({"website-accounts:manage", "courses:manage", "reports:operations:read"}), role_code="admin"),
        "teacher": EmployeePrincipal(30, frozenset({"leaves:approve", "tickets:write", "tickets:read"})),
        "employee": EmployeePrincipal(11),
        "advisor": EmployeePrincipal(12, frozenset({"applications:read", "applications:write", "academics:read", "academics:write", "student-alerts:read", "student-alerts:write"}), frozenset({21})),
    }

    def authenticate(self, token):
        if token not in actors:
            raise HTTPException(401, "登录无效")
        return actors[token]

    monkeypatch.setattr(auth_service.AuthService, "authenticate", authenticate)
    monkeypatch.setattr(visitor_router, "_AUTH_CAPACITY", visitor_router.CsChatCapacity(4, 2, 10))
    website = "/api/v1/visitors"
    management = "/api/v1/enterprise/website-accounts"
    student_api = "/api/v1/student"
    operator = {"Authorization": "Bearer operator"}
    teacher = {"Authorization": "Bearer teacher"}
    credentials = {"username": "13900002001", "password": "test-visitor-password"}

    def bearer(response):
        return {"Authorization": "Bearer " + response.json()["data"]["access_token"]}

    try:
        with Session(engine) as db:
            db.execute(text("""CREATE TABLE course_project (
                id INTEGER PRIMARY KEY, project_name TEXT, category TEXT, description TEXT,
                target_audience TEXT, duration TEXT, price NUMERIC, status INTEGER
            )"""))
            db.execute(text("""INSERT INTO course_project (id, project_name, category, status) VALUES
                (1, '德语入门', '语言', 1), (2, '下架课程', '语言', 0), (3, '留学项目', '项目', 1)
            """))
            db.execute(text("UPDATE course_project SET price=800 WHERE id=1"))
            db.execute(text("""CREATE TABLE report_schedule(
                id INTEGER PRIMARY KEY, report_type TEXT, schedule_cron TEXT, recipients JSON, enabled INTEGER,
                last_run_time DATETIME, create_time DATETIME, update_time DATETIME
            )"""))
            db.execute(text("""CREATE TABLE report_generation(
                id INTEGER PRIMARY KEY, report_type TEXT, report_title TEXT, report_content JSON,
                period_start DATE, period_end DATE, generated_by INTEGER, status TEXT, create_time DATETIME
            )"""))
            db.execute(text("""CREATE TABLE student_psych_record (
                id INTEGER PRIMARY KEY, student_id INTEGER, interaction_content TEXT, record_date DATE, create_time DATETIME
            )"""))
            db.execute(text("""CREATE TABLE student_psych_alert (
                id INTEGER PRIMARY KEY, student_id INTEGER, teacher_id INTEGER, risk_level TEXT, status TEXT,
                trigger_reason TEXT, follow_record TEXT, create_time DATETIME, update_time DATETIME, resolved_time DATETIME
            )"""))
            db.execute(text("""INSERT INTO student_psych_alert
                (id, student_id, teacher_id, risk_level, status, trigger_reason, create_time) VALUES
                (1, 21, 12, 'high', 'pending', '内部', '2026-11-13 09:00:00'),
                (2, 21, 13, 'high', 'pending', '其他老师', '2026-11-13 09:00:00')
            """))
            db.add_all([
                SysUser(id=21, real_name="李同学", user_type="student", status="normal"),
                SysUser(id=22, real_name="停用学生", user_type="student", status="disabled"),
                SysUser(id=23, real_name="其他同学", user_type="student", status="normal"),
                SysUser(id=30, real_name="班主任", user_type="employee", status="normal"),
            ])
            db.execute(text("CREATE TABLE student_info (user_id INTEGER, class_teacher_id INTEGER, abroad_country VARCHAR(64))"))
            db.execute(text("INSERT INTO student_info (user_id, class_teacher_id) VALUES (21, 30), (23, 30)"))
            db.commit()

        with TestClient(app) as client:
            signup = client.post(website + "/register", json={**credentials, "name": "李同学", "contact": "电话"})
            assert signup.status_code == 201 and signup.json()["data"]["account_type"] == "visitor"
            old_session = bearer(signup)
            courses_url = website + "/courses"
            assert client.get(courses_url).status_code == 401
            page = client.get(courses_url, params={"limit": 1}, headers=old_session).json()["data"]
            assert page["items"][0]["price"] is None
            assert page["items"][0]["project_name"] == "德语入门" and page["next_after_id"] == 1
            matches = client.get(courses_url, params={"keyword": "语言"}, headers=old_session).json()["data"]
            assert [item["id"] for item in matches["items"]] == [1]
            assert matches["next_after_id"] is None
            staff_courses = "/api/v1/enterprise/courses"
            course = {"project_name": "新课程", "status": 0, "price": 900}
            assert client.post(staff_courses, headers=old_session, json=course).status_code == 401
            saved_course = client.post(staff_courses, headers=operator, json=course)
            assert saved_course.status_code == 201
            assert saved_course.json()["data"]["price"] is None
            course_id = saved_course.json()["data"]["id"]
            assert client.get(courses_url, params={"keyword": "新课程"}, headers=old_session).json()["data"]["items"] == []
            assert client.put(f"{staff_courses}/{course_id}", headers=operator, json={**course, "status": 1}).status_code == 200
            assert len(client.get(courses_url, params={"keyword": "新课程"}, headers=old_session).json()["data"]["items"]) == 1
            with Session(engine) as db:
                assert db.execute(text("SELECT price FROM course_project WHERE id=:id"), {"id": course_id}).scalar_one() is None
                assert db.execute(text("SELECT price FROM course_project WHERE id=1")).scalar_one() == 800
            material = client.post("/api/v1/visitor/materials", data={"raw_content": "原资料"}, headers=old_session)
            assert material.status_code == 201
            material_id = material.json()["data"]["source_id"]
            assert client.get(student_api + "/leaves", headers=old_session).status_code == 403
            assert client.get(student_api + "/policies", headers=old_session).status_code == 403
            assert client.get(management, headers=old_session).status_code == 401
            assert client.get(management, headers={"Authorization": "Bearer employee"}).status_code == 403
            with Session(engine) as db:
                original_hash = db.scalar(select(VisitorAccount.password_hash).where(VisitorAccount.username == credentials["username"]))

            accounts = client.get(management, params={"keyword": "13900002001"}, headers=operator).json()["data"]
            visitor_id = accounts[0]["id"]
            assert "password_hash" not in accounts[0]
            update = f"{management}/{visitor_id}/student-access"
            listed = client.get(management + "/students", headers=operator).json()["data"]
            assert {row["id"] for row in listed} == {21, 23}
            for invalid_student in (22, 30):
                assert client.put(update, json={"student_id": invalid_student, "enabled": True}, headers=operator).status_code == 422

            change = {"student_id": 21, "enabled": True}
            assert client.put(update, json=change, headers=operator).status_code == 200
            assert client.get(website + "/me", headers=old_session).status_code == 401
            signed_in = client.post(website + "/login", json=credentials)
            assert signed_in.status_code == 200 and signed_in.json()["data"]["account_type"] == "student"
            active = bearer(signed_in)
            assert client.put(update, json=change, headers=operator).status_code == 200
            assert client.get(website + "/me", headers=active).json()["data"]["account_type"] == "student"
            assert client.get(f"/api/v1/visitor/materials/{material_id}", headers=active).status_code == 200
            assert client.get("/api/v1/auth/me", headers=active).status_code == 401
            progress = "/api/v1/student-admin/application-progress"
            advisor = {"Authorization": "Bearer advisor"}
            payload = {"target_school": "示例院校", "stage": "document_prep", "next_action": "准备材料"}
            assert client.post(progress + "/23", headers=advisor, json=payload).status_code == 403
            assert client.post(progress + "/21", headers=active, json=payload).status_code == 401
            created = client.post(progress + "/21", headers=advisor, json=payload)
            assert created.status_code == 201
            progress_id = created.json()["data"]["id"]
            assert client.put(f"{progress}/21/{progress_id}", headers=advisor,
                              json={**payload, "stage": "submitted"}).status_code == 200

            from datetime import timedelta
            from app.modules.student.models import AcademicDeadline
            from app.modules.student.service import _deadline_now
            now = _deadline_now()
            exam = {"title": "期末考试", "deadline_type": "exam", "deadline": (now + timedelta(days=2)).isoformat()}
            admin_deadlines = "/api/v1/student-admin/academic-deadlines"
            assert client.post(admin_deadlines + "/23", headers=advisor, json=exam).status_code == 403
            created_exam = client.post(admin_deadlines + "/21", headers=advisor, json=exam)

            assert created_exam.status_code == 201
            internal = "/api/v1/student-admin/psych-alerts"
            assert client.get(internal, headers=active).status_code == 401
            assert client.get(student_api + "/psych-alerts", headers=active).status_code == 404
            assert [row["id"] for row in client.get(internal, headers=advisor).json()["data"]] == [1]
            follow = {"status": "following", "follow_record": "已联系"}
            assert client.put(internal + "/2", headers=advisor, json=follow).status_code == 404
            assert client.put(internal + "/1", headers=advisor, json=follow).status_code == 200
            close = {"status": "resolved", "follow_record": "复核结案"}
            closed = client.put(internal + "/1", headers=advisor, json=close)
            entries = closed.json()["data"]["follow_record"].splitlines()
            assert len(entries) == 2
            assert entries[0].endswith("员工12：已联系")
            assert entries[1].endswith("员工12：复核结案")
            assert client.put(internal + "/1", headers=advisor, json=follow).status_code == 409
            exam_id = created_exam.json()["data"]["id"]
            with Session(engine) as db:
                db.add_all([
                    AcademicDeadline(title="共享", student_id=None, deadline_type="exam", deadline=now+timedelta(days=1),
                                     create_time=now, update_time=now),
                    AcademicDeadline(title="别人事项", student_id=23, deadline_type="paper", deadline=now+timedelta(days=1),
                                     create_time=now, update_time=now),
                ])
                db.commit()
            items = client.get(student_api + "/deadlines", headers=active).json()["data"]["items"]
            assert [item["title"] for item in items] == ["共享", "期末考试"]
            assert client.post(f"{student_api}/deadlines/{items[0]['id']}/complete", headers=active).status_code == 404
            update_exam = f"{admin_deadlines}/21/{exam_id}"
            assert client.put(update_exam, headers=advisor, json={**exam, "reminder_enabled": False}).status_code == 200
            assert len(client.get(student_api + "/deadlines", headers=active).json()["data"]["items"]) == 1
            assert client.put(update_exam, headers=advisor, json=exam).status_code == 200
            completion = f"{student_api}/deadlines/{exam_id}/complete"
            assert client.post(completion, headers=active).json()["data"]["status"] == "done"
            assert client.post(completion, headers=active).status_code == 200
            assert client.put(update_exam, headers=advisor, json=exam).status_code == 409
            assert len(client.get(student_api + "/deadlines", headers=active).json()["data"]["items"]) == 1
            assert len(client.get(student_api + "/deadlines?upcoming=false", headers=active).json()["data"]["items"]) == 2
            assert client.post(internal, headers=advisor, json={
                "student_id": 23, "risk_level": "low", "trigger_reason": "无权登记",
            }).status_code == 403
            own = client.post(internal, headers=advisor, json={
                "student_id": 21, "risk_level": "low", "trigger_reason": "老师人工观察",
            })
            assert own.status_code == 201
            with Session(engine) as db:
                assert db.scalar(text("SELECT student_id FROM student_psych_record")) == 21
            week = client.get(internal + "/weekly", params={
                "anchor": own.json()["data"]["create_time"][:10],
            }, headers=advisor).json()["data"]
            assert {"status": "pending", "risk_level": "low", "count": 1} in week["items"]
            operations = "/api/v1/reporting/operations"
            dates = {"start": now.date().isoformat(), "end": now.date().isoformat()}
            assert client.get(operations, params=dates, headers=advisor).status_code == 403
            report = client.get(operations, params=dates, headers=operator)
            assert report.status_code == 200 and report.json()["data"]["department"] is None
            from app.modules.statistics import scheduled
            from datetime import datetime
            freeze = datetime.combine(now.date(), datetime.min.time()).replace(hour=10)
            monkeypatch.setattr(scheduled, "_now", lambda: freeze)
            schedules = "/api/v1/reporting/schedules"
            archive = "/api/v1/reporting/archive"
            schedule = {"kind": "customer_ops", "run_at": "08:00"}
            assert client.get(schedules, headers=active).status_code == 401
            assert client.put(schedules, headers=advisor, json=schedule).status_code == 403
            reply = client.get(schedules, headers=advisor)
            assert [plan["kind"] for plan in reply.json()["data"]["items"]] == ["psych_weekly"]
            assert client.get(archive, headers=operator).json()["data"] == []
            with Session(engine) as db:
                from app.modules.statistics.scheduled_repository import record_report
                prior = (freeze.date() - timedelta(days=1)).isoformat()
                record_report(db, 10, "customer_ops", "经营分析", {
                    "period_start": prior, "period_end": prior, "scope_version": 1,
                    "department": None, "statistics": {"leads_by_status": {"new": 2}},
                }, freeze)
                db.commit()
            saved = client.get(archive, headers=operator).json()["data"]
            assert saved[0]["report_content"] == {"leads_by_status": {"new": 2}}
            assert client.get(archive, headers=advisor).json()["data"] == []

            progress_rows = client.get(student_api + "/application-progress", headers=active).json()["data"]
            assert len(progress_rows) == 1 and progress_rows[0]["stage"] == "submitted"
            assert "handler_id" not in progress_rows[0]
            assert client.get(student_api + "/application-progress", headers=old_session).status_code == 401
            assert client.get(student_api + "/policies", headers=active).json()["data"] == {
                "country": None, "resources": [],
            }

            leave_url = student_api + "/leaves"
            leave = {"leave_type": "personal", "start_time": "2099-12-10T09:00",
                     "end_time": "2099-12-10T11:00", "reason": "事假"}
            assert client.post(leave_url, json={**leave, "student_id": 23}, headers=active).status_code == 422
            submitted = client.post(leave_url, json=leave, headers=active)
            assert submitted.status_code == 201
            leave_id = submitted.json()["data"]["id"]
            approval = client.post(f"/api/v1/student-admin/leaves/{leave_id}/approve",
                                   json={"decision": "approved"}, headers=teacher)
            assert approval.status_code == 200
            assert client.get(leave_url, headers=active).json()["data"][0]["status"] == "approved"
            inbox = student_api + "/notifications"
            assert [item["title"] for item in client.get(inbox, headers=active).json()["data"]] == ["请假审批结果"]
            complaint_url = student_api + "/complaints"
            complaint = client.post(complaint_url, json={"category": "learning", "content": "学习反馈"}, headers=active)
            assert complaint.status_code == 201
            assert client.get(complaint_url, headers=active).json()["data"][0]["content"] == "学习反馈"
            ticket_url = "/api/v1/enterprise/tickets/" + str(complaint.json()["data"]["id"])
            assert client.patch(ticket_url, headers=teacher, json={"expected_status": "pending", "status": "processing"}).status_code == 200
            assert client.patch(ticket_url, headers=teacher, json={"expected_status": "processing", "status": "resolved", "solution": "已核实"}).status_code == 200
            assert {item["title"] for item in client.get(inbox, headers=active).json()["data"]} == {"请假审批结果", "投诉处理结果"}

            second = client.post(website + "/register", json={
                **credentials, "username": "13900002002", "name": "另一位", "contact": "电话",
            })
            assert second.status_code == 201
            second_id = client.get(management, params={"keyword": "13900002002"}, headers=operator).json()["data"][0]["id"]
            second_access = f"{management}/{second_id}/student-access"
            assert client.put(second_access, json=change, headers=operator).status_code == 409
            assert client.put(second_access, json={"student_id": 23, "enabled": True}, headers=operator).status_code == 200
            second_login = client.post(website + "/login", json={**credentials, "username": "13900002002"})
            assert client.get(leave_url, headers=bearer(second_login)).json()["data"] == []
            assert client.get(complaint_url, headers=bearer(second_login)).json()["data"] == []
            assert client.get(inbox, headers=bearer(second_login)).json()["data"] == []
            from app.modules.student.service import scan_academic_reminders
            next_exam = {**exam, "title": "下次考试"}
            assert client.post(admin_deadlines + "/21", headers=advisor, json=next_exam).status_code == 201
            with Session(engine) as db:
                assert scan_academic_reminders(db) == 2
                assert scan_academic_reminders(db) == 0
            reminders = [row for row in client.get(inbox, headers=active).json()["data"] if row["title"] == "考务即将截止"]
            assert len(reminders) == 1 and "下次考试" in reminders[0]["content"]
            assert client.get(student_api + "/application-progress", headers=bearer(second_login)).json()["data"] == []

            assert client.put(update, json={**change, "enabled": False}, headers=operator).status_code == 200
            assert client.get(leave_url, headers=active).status_code == 401
            visitor_login = client.post(website + "/login", json=credentials)
            assert visitor_login.json()["data"]["account_type"] == "visitor"
            assert client.get(leave_url, headers=bearer(visitor_login)).status_code == 403

        with Session(engine) as db:
            assert db.scalar(select(VisitorAccount.password_hash).where(VisitorAccount.id == visitor_id)) == original_hash
            assert len(db.execute(select(audit_log.c.id).where(audit_log.c.action == "website_student_access")).all()) == 3
            todos = db.execute(select(todo_item.c.assignee_id, todo_item.c.status)).all()
            assert sorted(todos) == [(30, "done"), (30, "done")]
    finally:
        engine.dispose()


def test_staff_can_enroll_unlinked_visitor_and_keep_website_credentials(isolated_portal, monkeypatch):
    app, engine = isolated_portal("trusted_jwt")
    staff = EmployeePrincipal(10, frozenset({"website-accounts:manage"}))
    monkeypatch.setattr(auth_service.AuthService, "authenticate", lambda self, token: staff)
    monkeypatch.setattr(visitor_router, "_AUTH_CAPACITY", visitor_router.CsChatCapacity(4, 2, 10))
    staff_headers = {"Authorization": "Bearer staff"}
    credentials = {"username": "13900002003", "password": "test-website-password"}
    auth = "/api/v1/visitors"
    management = "/api/v1/enterprise/website-accounts"

    def bearer(reply):
        return {"Authorization": "Bearer " + reply.json()["data"]["access_token"]}

    try:
        with Session(engine) as db:
            db.execute(text("ALTER TABLE sys_user ADD COLUMN username VARCHAR(64)"))
            db.execute(text("ALTER TABLE sys_user ADD COLUMN password_hash VARCHAR(255)"))
            db.execute(text("ALTER TABLE sys_user ADD COLUMN role_id INTEGER"))
            db.execute(text("ALTER TABLE sys_user ADD COLUMN create_time DATETIME"))
            db.execute(text("ALTER TABLE sys_user ADD COLUMN update_time DATETIME"))
            db.execute(text("CREATE TABLE student_info (user_id INTEGER UNIQUE, class_teacher_id INTEGER, abroad_country VARCHAR(64))"))
            db.execute(text("""CREATE TABLE overseas_life_knowledge (
                id INTEGER PRIMARY KEY, country TEXT, category TEXT, title TEXT, content TEXT, status INTEGER
            )"""))
            db.execute(text("""INSERT INTO overseas_life_knowledge VALUES
                (1, 'Germany', 'transport', '德国出行', '本地交通', 1),
                (2, '新加坡', 'transport', '新加坡出行', '本地交通', 1),
                (3, 'Germany', 'transport', '停用资料', '停用', 0)
            """))
            db.execute(roles.insert(), [
                {"id": 5, "role_code": "team_leader", "role_name": "班主任"},
                {"id": 6, "role_code": "student", "role_name": "学生"},
            ])
            db.execute(role_permissions.insert(), [
                {"role_id": 5, "permission": value}
                for value in ("leaves:read", "leaves:approve", "tickets:read", "tickets:write")
            ])
            db.execute(text("""INSERT INTO sys_user (id, real_name, user_type, status, role_id) VALUES
                (30, '班主任甲', 'employee', 'normal', 5), (31, '普通员工', 'employee', 'normal', NULL),
                (32, '停用老师', 'employee', 'disabled', 5)"""))
            db.commit()

        with TestClient(app, raise_server_exceptions=False) as client:
            signup = client.post(auth + "/register", json={**credentials, "name": "新同学", "contact": "电话"})
            assert signup.status_code == 201
            public_policies = auth + "/policies"
            assert client.get(public_policies, params={"country": "Germany"}).status_code == 401
            portal_policy = client.get(public_policies, params={"country": "Germany"}, headers=bearer(signup))
            assert portal_policy.json()["data"]["country"] == "Germany"
            assert client.get(public_policies, params={"country": "invalid"}, headers=bearer(signup)).status_code == 422
            listed = client.get(management, headers=staff_headers).json()["data"]
            visitor_id = listed[0]["id"]
            teachers = client.get(management + "/teachers", headers=staff_headers).json()["data"]
            assert teachers == [{"id": 30, "real_name": "班主任甲"}]
            url = f"{management}/{visitor_id}/student-access"
            fields = {"class_teacher_id": 30, "abroad_country": "Germany"}
            assert client.post(url, json={**fields, "class_teacher_id": 31}, headers=staff_headers).status_code == 422
            assert client.post(url, json={**fields, "abroad_country": "invalid"}, headers=staff_headers).status_code == 422
            assert client.post(url, json={**fields, "password": "injected"}, headers=staff_headers).status_code == 422

            def fail_profile(*args):
                raise RuntimeError("profile write unavailable")

            with monkeypatch.context() as context:
                context.setattr(visitor_repository, "create_student_profile", fail_profile)
                assert client.post(url, json=fields, headers=staff_headers).status_code == 500
            with Session(engine) as db:
                assert db.scalar(select(SysUser.id).where(SysUser.user_type == "student")) is None

            saved = client.post(url, json=fields, headers=staff_headers)
            assert saved.status_code == 201
            student_id = saved.json()["data"]["student_id"]
            assert client.post(url, json=fields, headers=staff_headers).status_code == 409
            assert client.get(auth + "/me", headers=bearer(signup)).status_code == 401
            logged_in = client.post(auth + "/login", json=credentials)
            assert logged_in.json()["data"]["account_type"] == "student"
            session = bearer(logged_in)
            profile = client.get("/api/v1/student/profile", headers=session)
            assert profile.json()["data"] == {"abroad_country": "Germany"}
            policies_url = "/api/v1/student/policies"
            life_url = "/api/v1/student/overseas-life"
            assert [item["title"] for item in client.get(life_url, headers=session).json()["data"]["items"]] == ["德国出行"]
            germany = client.get(policies_url, params={"country": "Singapore"}, headers=session).json()["data"]
            assert germany["country"] == "Germany"
            assert any("make-it-in-germany.com" in row["url"] for row in germany["resources"])
            assert all("ica.gov.sg" not in row["url"] for row in germany["resources"])
            with Session(engine) as db:
                db.execute(text("UPDATE student_info SET abroad_country=:country WHERE user_id=:id"),
                           {"country": " 新加坡 ", "id": student_id})
                db.commit()
            singapore = client.get(policies_url, headers=session).json()["data"]
            assert singapore["country"] == "Singapore"
            assert all("ica.gov.sg" in row["url"] for row in singapore["resources"])
            assert singapore["resources"]
            assert [item["title"] for item in client.get(life_url, headers=session).json()["data"]["items"]] == ["新加坡出行"]
            leave = client.post("/api/v1/student/leaves", headers=session, json={
                "leave_type": "personal", "start_time": "2099-12-10T09:00",
                "end_time": "2099-12-10T11:00", "reason": "事假",
            })
            assert leave.status_code == 201
            assert leave.json()["data"]["approver_id"] == 30

        with Session(engine) as db:
            account = db.execute(text("SELECT username, password_hash FROM sys_user WHERE id=:id"),
                                 {"id": student_id}).one()
            assert account.username != credentials["username"]
            registered_hash = db.scalar(select(VisitorAccount.password_hash).where(VisitorAccount.id == visitor_id))
            assert account.password_hash != registered_hash
            assert db.scalar(select(audit_log.c.actor_id).where(audit_log.c.action == "website_student_access")) == 10
    finally:
        engine.dispose()

def test_admin_resets_website_password_and_revokes_all_sessions(isolated_portal, monkeypatch):
    app, engine = isolated_portal("trusted_jwt")
    actors = {
        "admin": EmployeePrincipal(10, frozenset({"website-accounts:manage"}), role_code="admin"),
        "staff": EmployeePrincipal(11, role_code="employee"),
    }

    def authenticate(self, token):
        if token not in actors:
            raise HTTPException(401, "登录无效")
        return actors[token]

    monkeypatch.setattr(auth_service.AuthService, "authenticate", authenticate)
    website = "/api/v1/visitors"
    management = "/api/v1/enterprise/website-accounts"
    monkeypatch.setattr(visitor_router, "_AUTH_CAPACITY", visitor_router.CsChatCapacity(4, 2, 10))
    admin = {"Authorization": "Bearer admin"}
    staff = {"Authorization": "Bearer staff"}
    credentials = {"username": "13900002004", "password": "original-test-password"}
    new_password = "YJ" + credentials["username"][-6:]

    def bearer(response):
        return {"Authorization": "Bearer " + response.json()["data"]["access_token"]}

    try:
        with Session(engine) as db:
            db.add(SysUser(id=21, real_name="测试学生", user_type="student", status="normal"))
            db.add(VisitorAccount(username="legacy-visitor", name="旧账号", contact="旧联系方式",
                                  password_hash=hash_password("legacy-test-password"), created_at=utc_now()))
            db.commit()

        with TestClient(app) as client:
            registration = credentials.copy()
            bad_phone = client.post(website + "/register", json={**registration, "username": "bad-phone"})
            assert bad_phone.status_code == 422 and credentials["password"] not in bad_phone.text
            assert client.post(website + "/register", json={**registration, "password": "123456"}).status_code == 422
            signup = client.post(website + "/register", json=registration)
            assert signup.status_code == 201
            account = client.get(management, headers=admin, params={"keyword": credentials["username"]}).json()["data"][0]
            assert account["contact"] == credentials["username"]
            assert account["name"] == "未填写姓名"
            visitor_id = account["id"]
            reset = f"{management}/{visitor_id}/password"
            assert client.post(reset, headers=bearer(signup), json={}).status_code == 401
            assert client.post(reset, headers=staff, json={}).status_code == 403
            invalid = client.post(reset, headers=admin, json={"new_password": "onlyletters"})
            assert invalid.status_code == 422 and "onlyletters" not in invalid.text
            assert client.post(f"{management}/{visitor_id + 1000}/password", headers=admin,
                               json={}).status_code == 404
            enabled = client.put(f"{management}/{visitor_id}/student-access", headers=admin,
                                 json={"student_id": 21, "enabled": True})
            assert enabled.status_code == 200
            login_one = client.post(website + "/login", json=credentials)
            login_two = client.post(website + "/login", json=credentials)
            assert login_one.status_code == login_two.status_code == 200
            assert login_one.json()["data"]["account_type"] == "student"

            assert client.post(reset, headers=admin, json={"new_password": "manual-test-password"}).status_code == 422
            changed = client.post(reset, headers=admin, json={})
            assert changed.status_code == 200
            assert changed.json()["data"] == {"id": visitor_id, "sessions_revoked": True}
            assert new_password not in changed.text
            for login in (login_one, login_two):
                assert client.get(website + "/me", headers=bearer(login)).status_code == 401
            assert client.post(website + "/login", json=credentials).status_code == 401
            authenticated = client.post(website + "/login", json={**credentials, "password": new_password})
            assert authenticated.status_code == 200
            assert authenticated.json()["data"]["account_type"] == "student"
            legacy_login = client.post(website + "/login", json={
                "username": "legacy-visitor", "password": "legacy-test-password",
            })
            assert legacy_login.status_code == 422
            legacy_account = client.get(management, headers=admin, params={"keyword": "legacy-visitor"}).json()["data"][0]
            legacy_reset = f"{management}/{legacy_account['id']}/password"
            assert client.post(legacy_reset, headers=admin, json={}).status_code == 422
            assert client.post(legacy_reset, headers=admin, json={"new_password": "legacy-reset-password"}).status_code == 422

        with Session(engine) as db:
            row = db.execute(select(audit_log).where(audit_log.c.action == "website_password_reset",
                                                    audit_log.c.target == str(visitor_id))).mappings().one()
            assert row["actor_id"] == 10 and row["target"] == str(visitor_id)
            assert row["details"] == "{}"
    finally:
        engine.dispose()



@pytest.mark.parametrize("is_student", [False, True])
def test_website_account_can_change_its_own_password(isolated_portal, monkeypatch, is_student):
    app, engine = isolated_portal("trusted_jwt")
    monkeypatch.setattr(visitor_router, "_AUTH_CAPACITY", visitor_router.CsChatCapacity(4, 2, 10))
    website = "/api/v1/visitors"
    registration = {"username": "13900003018", "password": "guest-pass", "nickname": "  测试昵称  "}

    def bearer(response):
        return {"Authorization": "Bearer " + response.json()["data"]["access_token"]}

    try:
        with TestClient(app) as client:
            for invalid in ("12345678", "Abcd 123", "Abcd中文23", "Abcd\u200b123", "A1" * 65):
                rejected = client.post(website + "/register", json={**registration, "password": invalid})
                assert rejected.status_code == 422
                assert all("input" not in entry for entry in rejected.json()["detail"])
            for invalid_nickname in ("   ", "名" * 65):
                assert client.post(website + "/register", json={
                    **registration, "nickname": invalid_nickname,
                }).status_code == 422
            signup = client.post(website + "/register", json=registration)
            assert signup.status_code == 201
            first = bearer(signup)
            account = client.get(website + "/profile", headers=first).json()["data"]
            assert account["nickname"] == "测试昵称"
            assert account["name"] == ""
            if is_student:
                with Session(engine) as db:
                    visitor_id = db.scalar(select(VisitorAccount.id).where(
                        VisitorAccount.username == registration["username"],
                    ))
                    db.add(SysUser(id=55, real_name="测试学生", user_type="student", status="normal"))
                    db.flush()
                    db.add(WebsiteStudentAccess(visitor_id=visitor_id, student_id=55, enabled=True))
                    db.commit()
            credentials = {key: registration[key] for key in ("username", "password")}
            second = bearer(client.post(website + "/login", json=credentials))
            endpoint = website + "/password"
            new = {"old_password": credentials["password"], "new_password": "Abcd1234"}
            assert client.post(endpoint, json=new).status_code == 401
            assert client.post(endpoint, headers=first, json={**new, "old_password": "incorrect"}).status_code == 400
            assert client.post(endpoint, headers=first, json={**new, "new_password": "onlyletters"}).status_code == 422
            changed = client.post(endpoint, headers=first, json=new)
            assert changed.status_code == 200 and changed.json()["data"] == {"relogin_required": True}
            for prior in (first, second):
                assert client.get(website + "/me", headers=prior).status_code == 401
            assert client.post(website + "/login", json=credentials).status_code == 401
            login = client.post(website + "/login", json={**credentials, "password": new["new_password"]})
            assert login.status_code == 200
            assert login.json()["data"]["account_type"] == ("student" if is_student else "visitor")
    finally:
        engine.dispose()
