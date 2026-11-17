from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.security import EmployeePrincipal
from app.core.security.credentials import utc_now
from app.modules.auth import service as auth_service
from app.modules.auth.models import role_permissions, roles
from app.modules.auth.repository import AuthRepository
from app.modules.classroom.models import ClassEnrollment
from app.modules.consultant.models import CrmLead, VisitorIntake
from app.modules.feedback.models import student_feedback_ticket
from app.modules.student_admin.models import StudentAdminService
from app.modules.todo.models import todo_item
from app.modules.visitor.models import VisitorAccount
from tests.integration.test_ent_portal_routes import isolated_portal


def test_project_class_conversion_and_teacher_reassignment(isolated_portal, monkeypatch):
    app, engine = isolated_portal("trusted_jwt")
    actors = {
        "admin": EmployeePrincipal(10, frozenset({"classes:manage", "website-accounts:manage"})),
        "staff": EmployeePrincipal(11),
    }
    monkeypatch.setattr(auth_service.AuthService, "authenticate", lambda self, token: actors[token])
    now = utc_now()
    with Session(engine) as db:
        db.execute(text("ALTER TABLE sys_user ADD COLUMN username VARCHAR(64)"))
        db.execute(text("ALTER TABLE sys_user ADD COLUMN password_hash VARCHAR(255)"))
        db.execute(text("ALTER TABLE sys_user ADD COLUMN role_id INTEGER"))
        db.execute(text("ALTER TABLE sys_user ADD COLUMN create_time DATETIME"))
        db.execute(text("ALTER TABLE sys_user ADD COLUMN update_time DATETIME"))
        db.execute(text("""CREATE TABLE student_info (
            user_id INTEGER UNIQUE, class_teacher_id INTEGER, abroad_country TEXT, student_no TEXT
        )"""))
        db.execute(text("CREATE TABLE course_project (id INTEGER PRIMARY KEY, project_name TEXT, status INTEGER)"))
        db.execute(text("CREATE TABLE student_psych_alert (id INTEGER PRIMARY KEY, student_id INTEGER, teacher_id INTEGER, status TEXT)"))
        db.execute(text("INSERT INTO course_project VALUES (1, '德国项目', 1), (2, '新加坡项目', 1)"))
        db.execute(roles.insert(), [
            {"id": 5, "role_code": "team_leader", "role_name": "班主任"},
            {"id": 6, "role_code": "student", "role_name": "学生"},
        ])
        db.execute(role_permissions.insert(), [
            {"role_id": 5, "permission": permission}
            for permission in ("leaves:read", "leaves:approve", "tickets:read", "tickets:write")
        ])
        db.execute(text("""INSERT INTO sys_user (id, real_name, user_type, status, role_id) VALUES
            (30, '班主任甲', 'employee', 'normal', 5), (31, '班主任乙', 'employee', 'normal', 5)
        """))
        visitor = VisitorAccount(username="13900003001", name="学生甲", contact="测试", password_hash="unused",
                                 created_at=now)
        lead = CrmLead(customer_name="学生甲", owner_employee_id=11, create_time=now, update_time=now)
        db.add_all([visitor, lead])
        db.flush()
        visitor_id = visitor.id
        db.add(VisitorIntake(visitor_id=visitor.id, advisor_id=11, claimed_at=now, crm_lead_id=lead.id))
        sibling_visitor = VisitorAccount(username="13900003002", name="学生乙", contact="测试",
                                         password_hash="unused", created_at=now)
        db.add(sibling_visitor)
        db.flush()
        sibling_visitor_id = sibling_visitor.id
        db.commit()

    admin = {"Authorization": "Bearer admin"}
    root = "/api/v1/enterprise/classrooms"
    access = f"/api/v1/enterprise/website-accounts/{visitor_id}/student-access"
    with TestClient(app) as client:
        assert client.get(root + "/projects", headers={"Authorization": "Bearer staff"}).status_code == 403
        assert client.post(root, json={"project_id": 1, "name": "一班"}, headers=admin).status_code == 422
        assert client.get(root + "/enrollment-projects", headers=admin).json()["data"] == []
        for project, country in [(1, "Germany"), (2, "Singapore")]:
            setting = client.put(f"{root}/projects/{project}",
                                 json={"abroad_country": country}, headers=admin)
            assert setting.status_code == 200, setting.text

        classes = []
        for project in range(1, 3):
            response = client.post(root, json={"project_id": project, "name": "一班", "teacher_id": 30}, headers=admin)
            assert response.status_code == 201, response.text
            classes.append(response.json()["data"]["id"])
        assert client.post(root, json={"project_id": 1, "name": "一班", "teacher_id": 30}, headers=admin).status_code == 409
        assert client.post(root, json={"project_id": 1, "name": "二班", "teacher_id": 999}, headers=admin).status_code == 422
        sibling = client.post(root, json={"project_id": 1, "name": "二班", "teacher_id": 31}, headers=admin)
        assert sibling.status_code == 201, sibling.text
        sibling_id = sibling.json()["data"]["id"]
        choices = client.get(f"{root}/enrollment-projects/1/classes", headers=admin).json()["data"]
        assert {row["id"]: row["teacher_id"] for row in choices} == {classes[0]: 30, sibling_id: 31}
        assert client.post(access, json={"class_teacher_id": 30, "abroad_country": "Germany"},
                           headers=admin).status_code == 422
        assert client.post(access, json={"project_id": 1, "class_id": classes[1]}, headers=admin).status_code == 422
        assert client.put(f"{root}/{classes[0]}", json={"name": "一班", "teacher_id": 30, "enabled": False},
                          headers=admin).status_code == 200
        assert client.post(access, json={"project_id": 1, "class_id": classes[0]}, headers=admin).status_code == 422
        assert client.put(f"{root}/{classes[0]}", json={"name": "一班", "teacher_id": 30, "enabled": True},
                          headers=admin).status_code == 200

        response = client.post(access, json={"project_id": 1, "class_id": classes[0]}, headers=admin)
        assert response.status_code == 201, response.text
        student_id = response.json()["data"]["student_id"]
        sibling_access = f"/api/v1/enterprise/website-accounts/{sibling_visitor_id}/student-access"
        sibling_saved = client.post(sibling_access, json={"project_id": 1, "class_id": sibling_id}, headers=admin)
        assert sibling_saved.status_code == 201, sibling_saved.text
        sibling_student = sibling_saved.json()["data"]["student_id"]
        roster = client.get(f"{root}/{classes[0]}/students", headers=admin).json()["data"]
        assert roster == [{"id": student_id, "real_name": "学生甲", "student_no": None}]
        assert client.post(access, json={"project_id": 1, "class_id": classes[0]}, headers=admin).status_code == 409
        with Session(engine) as db:
            assert AuthRepository(db).scope(30) == {student_id}
            assert AuthRepository(db).scope(31) == {sibling_student}
            leave = StudentAdminService(
                student_id=student_id, service_type="leave", reason="事假", status="pending",
                approver_id=30, create_time=now, update_time=now,
            )
            db.add(leave)
            db.flush()
            leave_id = leave.id
            db.execute(student_feedback_ticket.insert(), [
                {"student_id": student_id, "category": category, "ticket_type": "complaint",
                 "content": "测试", "status": "pending", "priority": "medium", "assignee_id": 30,
                 "is_notified": 0, "create_time": now, "update_time": now}
                for category in ("learning", "company")
            ])
            db.commit()
        assert client.put(f"{root}/projects/1",
                          json={"abroad_country": "Singapore"}, headers=admin).status_code == 409
        assert client.put(f"{root}/{classes[0]}",
                          json={"name": "一班", "teacher_id": 31, "enabled": True}, headers=admin).status_code == 200
        with Session(engine) as db:
            assert db.scalar(select(ClassEnrollment.class_id).where(ClassEnrollment.student_id == student_id)) == classes[0]
            assert AuthRepository(db).scope(30) == set()
            assert AuthRepository(db).scope(31) == {student_id, sibling_student}
            assert db.get(StudentAdminService, leave_id).approver_id == 31
            tickets = dict(db.execute(select(student_feedback_ticket.c.category, student_feedback_ticket.c.assignee_id)).all())
            assert tickets == {"learning": 31, "company": 30}
            assert set(db.scalars(select(todo_item.c.assignee_id))) == {31}
        assert client.put(f"{root}/{sibling_id}",
                          json={"name": "二班", "teacher_id": 30, "enabled": True}, headers=admin).status_code == 200
        with Session(engine) as db:
            assert AuthRepository(db).scope(30) == {sibling_student}
            assert AuthRepository(db).scope(31) == {student_id}
    engine.dispose()
