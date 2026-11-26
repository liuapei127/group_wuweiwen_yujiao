"""Teacher workflows on an isolated database, including transfer and trust boundaries."""
from datetime import timedelta
from base64 import b64decode
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import EmployeePrincipal
from app.core.security.credentials import utc_now
from app.core.security.rbac import ROLE_DEFAULTS
from app.modules.auth import service as auth_service
from app.modules.auth.models import accounts, audit_log, role_permissions, roles, student_scopes
from app.modules.auth.repository import AuthRepository
from app.modules.classroom.models import ClassEnrollment, ClassPlacementHistory, ProjectClass, TeachingProject
from app.modules.consultant.models import CrmLead, VisitorIntake
from app.modules.feedback import service as feedback_service
from app.modules.feedback.models import student_feedback_ticket
from app.modules.statistics.wellbeing_models import WellbeingCase, WellbeingFollowup
from app.modules.student.models import AcademicDeadline
from app.modules.student_admin.models import StudentAdminService
from app.modules.todo.models import todo_item
from app.modules.visitor import service as visitor_service
from app.modules.visitor.models import VisitorAccount, VisitorSession, WebsiteStudentAccess
from tests.integration.test_ent_portal_routes import isolated_portal


def auth(token):
    return {"Authorization": "Bearer " + token}


@pytest.fixture
def teacher_world(isolated_portal, monkeypatch):
    app, engine = isolated_portal("trusted_jwt")
    now = utc_now()
    with Session(engine) as db:
        for name, kind in [("username", "TEXT"), ("password_hash", "TEXT"), ("role_id", "INTEGER"),
                           ("avatar_url", "TEXT"), ("create_time", "DATETIME"), ("update_time", "DATETIME")]:
            db.execute(text(f"ALTER TABLE sys_user ADD COLUMN {name} {kind}"))
        db.execute(text("""CREATE TABLE student_info (user_id INTEGER UNIQUE, class_teacher_id INTEGER,
            abroad_country TEXT, student_no TEXT, school TEXT, major TEXT)"""))
        db.execute(text("CREATE TABLE course_project (id INTEGER PRIMARY KEY, project_name TEXT, status INTEGER)"))
        db.execute(text("""CREATE TABLE student_psych_alert (id INTEGER PRIMARY KEY, student_id INTEGER,
            teacher_id INTEGER, status TEXT, risk_level TEXT DEFAULT 'high', trigger_reason TEXT DEFAULT '测试观察',
            follow_record TEXT, create_time DATETIME DEFAULT CURRENT_TIMESTAMP, update_time DATETIME, resolved_time DATETIME)"""))
        db.execute(text("""CREATE TABLE student_psych_record (id INTEGER PRIMARY KEY, student_id INTEGER,
            emotion_tag TEXT, emotion_score INTEGER, interaction_content TEXT, record_date DATE, create_time DATETIME)"""))
        for rid, code in [(1, "admin"), (2, "employee"), (3, "manager"), (5, "team_leader"), (6, "student")]:
            db.execute(roles.insert().values(id=rid, role_code=code, role_name=code, status=1))
            grants = ROLE_DEFAULTS[code]
            if grants:
                db.execute(role_permissions.insert(), [{"role_id": rid, "permission": g} for g in grants])
        for uid, rid, kind in [(10, 1, "admin"), (11, 3, "employee"), (12, 2, "employee"),
                               (30, 5, "employee"), (31, 5, "employee"), (21, 6, "student"), (22, 6, "student")]:
            db.execute(accounts.insert().values(id=uid, username=f"1390000{uid:04}", password_hash="unused",
                real_name=f"人员{uid}", role_id=rid, user_type=kind, status="normal", create_time=now, update_time=now))
        db.execute(text("INSERT INTO course_project VALUES (1, '预科项目', 1), (2, '留学项目', 1)"))
        db.add_all([TeachingProject(project_id=1, abroad_country="Germany"), TeachingProject(project_id=2, abroad_country="Singapore"),
                    ProjectClass(id=1, project_id=1, name="一班", teacher_id=30, enabled=True),
                    ProjectClass(id=2, project_id=2, name="二班", teacher_id=31, enabled=True),
                    ClassEnrollment(student_id=21, class_id=1), ClassEnrollment(student_id=22, class_id=2)])
        db.execute(text("INSERT INTO student_info VALUES (21,30,'Germany','S21','测试学校','测试专业'), (22,31,'Singapore','S22',NULL,NULL)"))
        # An old manual grant must not let a teacher view another teacher's students.
        db.execute(student_scopes.insert().values(user_id=30, student_id=22))
        for vid, sid in [(101, 21), (102, 22)]:
            db.add(VisitorAccount(id=vid, username=str(vid), name=f"学生{sid}", contact="测试", password_hash="unused", created_at=now))
            db.add(VisitorSession(digest=str(vid), visitor_id=vid, expires_at=now + timedelta(hours=1)))
            db.add(WebsiteStudentAccess(visitor_id=vid, student_id=sid, enabled=True))
        lead = CrmLead(customer_name="学生21", owner_employee_id=12, create_time=now, update_time=now)
        db.add(lead); db.flush()
        db.add(VisitorIntake(visitor_id=101, advisor_id=12, claimed_at=now, crm_lead_id=lead.id))
        db.commit()

    identities = {"admin": 10, "manager": 11, "advisor": 12, "teacher": 30, "other": 31}
    def authenticate(self, token):
        uid = identities[token]
        account = self.repo.account(user_id=uid)
        return EmployeePrincipal(uid, frozenset(self.repo.permissions(account["role_id"])),
            frozenset(self.repo.scope(uid)), role_code=account["role_code"])
    monkeypatch.setattr(auth_service.AuthService, "authenticate", authenticate)
    monkeypatch.setattr(visitor_service, "authenticate", lambda db, token: visitor_service.VisitorPrincipal(int(token), token))
    monkeypatch.setattr(feedback_service, "get_settings", lambda: Settings(_env_file=None, company_complaint_manager_id=11))
    with TestClient(app) as client:
        yield client, engine
    engine.dispose()


def test_directory_application_ownership_and_profile(teacher_world):
    client, engine = teacher_world
    assert [r["id"] for r in client.get("/api/v1/teacher/classes", headers=auth("teacher")).json()["data"]] == [1]
    listing = client.get("/api/v1/teacher/students", headers=auth("teacher"))
    assert listing.status_code == 200, listing.text
    assert [r["id"] for r in listing.json()["data"]["items"]] == [21]
    assert client.get("/api/v1/teacher/students/22", headers=auth("teacher")).status_code == 403
    assert client.get("/api/v1/teacher/students?class_id=2", headers=auth("teacher")).status_code == 404
    progress = {"target_school": "测试院校", "stage": "document_prep", "next_action": "准备材料"}
    url = "/api/v1/student-admin/application-progress/21"
    assert client.post(url, json=progress, headers=auth("advisor")).status_code == 403
    assert client.post(url, json=progress, headers=auth("teacher")).status_code == 201
    assert len(client.get(url, headers=auth("advisor")).json()["data"]) == 1
    assert client.get(url.replace("21", "22"), headers=auth("advisor")).status_code == 403
    assert client.patch("/api/v1/auth/profile", json={"real_name": "班主任新名", "contact_info": "13900000000"}, headers=auth("teacher")).status_code == 200
    assert client.patch("/api/v1/auth/profile", json={"real_name": "越权", "role_id": 1}, headers=auth("teacher")).status_code == 422


def test_student_record_names_are_current_and_keep_existing_visibility(teacher_world):
    client, engine = teacher_world
    now = utc_now()
    names = {21: '陈思远', 22: '林予安'}
    with Session(engine) as db:
        for sid, teacher, record_id in ((21, 30, 1), (22, 31, 2)):
            db.execute(accounts.update().where(accounts.c.id == sid).values(real_name=names[sid]))
            db.add(StudentAdminService(id=record_id, student_id=sid, service_type='leave', reason='办理材料',
                status='pending', approver_id=teacher, create_time=now, update_time=now))
            db.execute(student_feedback_ticket.insert().values(id=record_id, student_id=sid, ticket_type='complaint',
                category='learning', content='课程反馈', status='pending', priority='medium', assignee_id=teacher,
                is_notified=0, create_time=now, update_time=now))
            db.execute(text('INSERT INTO student_psych_alert (id,student_id,teacher_id,status) VALUES (:id,:sid,:teacher,\'pending\')'),
                {'id': record_id, 'sid': sid, 'teacher': teacher})
            db.add(WellbeingCase(id=record_id, student_id=sid, status='open', note='学习关怀', assigned_to=teacher, created_at=now))
        db.commit()

    list_paths = [
        '/api/v1/student-admin/psych-alerts',
        '/api/v1/enterprise/tickets',
        '/api/v1/student-admin/leaves/pending',
        '/api/v1/reporting/wellbeing/cases',
    ]
    detail_paths = ['/api/v1/enterprise/tickets/1', '/api/v1/student-admin/leaves/1', '/api/v1/reporting/wellbeing/cases/1']

    def verify_visible(expected_name):
        for path in list_paths:
            response = client.get(path, headers=auth('teacher'))
            assert response.status_code == 200, response.text
            data = response.json()['data']
            rows = data['items'] if isinstance(data, dict) else data
            assert [(row['student_id'], row['student_name']) for row in rows] == [(21, expected_name)]
            assert names[22] not in response.text
        for path in detail_paths:
            response = client.get(path, headers=auth('teacher'))
            assert response.status_code == 200, response.text
            assert response.json()['data']['student_name'] == expected_name

    verify_visible(names[21])
    for path in detail_paths:
        denied = client.get(path[:-1] + '2', headers=auth('teacher'))
        assert denied.status_code in (403, 404)
        assert names[22] not in denied.text
    denied = client.get('/api/v1/student-admin/psych-alerts?student_id=22', headers=auth('teacher'))
    assert denied.status_code == 403 and names[22] not in denied.text
    routing = client.get('/api/v1/enterprise/ticket-routing', headers=auth('admin'))
    assert {row['student_id']: row['student_name'] for row in routing.json()['data']} == names

    with Session(engine) as db:
        db.execute(accounts.update().where(accounts.c.id == 21).values(real_name='陈予安'))
        db.commit()
    verify_visible('陈予安')


def test_three_stage_courses_scores_and_class_deadline_replay(teacher_world):
    client, engine = teacher_world
    courses = []
    for phase in ("preparatory", "language", "overseas"):
        body = {"name": "课程" + phase, "study_stage": phase, "enabled": True}
        assert client.post("/api/v1/teaching/courses", json=body, headers=auth("teacher")).status_code == 403
        response = client.post("/api/v1/teaching/courses", json=body, headers=auth("admin"))
        assert response.status_code == 201, response.text
        courses.append(response.json()["data"]["id"])
    assert client.put("/api/v1/teaching/classes/1/courses", json={"course_ids": courses}, headers=auth("admin")).status_code == 200
    assert client.post("/api/v1/enterprise/scores", json={"student_id": 21, "course_name": "老师自行创建课程", "score": 90}, headers=auth("teacher")).status_code == 422
    assert client.get("/api/v1/teaching/students/22/courses", headers=auth("teacher")).status_code == 403
    body = {"student_id": 21, "course_id": courses[0], "semester": "2026秋", "score": "85", "submission_key": "phase-score"}
    response = client.post("/api/v1/enterprise/scores", json=body, headers=auth("teacher"))
    assert response.status_code == 200, response.text
    saved = response.json()["data"]
    assert client.post("/api/v1/enterprise/scores", json=body, headers=auth("teacher")).json()["data"]["id"] == saved["id"]
    rows = client.get("/api/v1/enterprise/scores?student_id=21", headers=auth("teacher")).json()["data"]
    assert rows[0]["study_stage"] == "preparatory"
    assert rows[0]["course_name"] == "课程preparatory"
    for course_id in courses[1:]:
        response = client.post("/api/v1/enterprise/scores", json={**body, "course_id": course_id, "submission_key": f"phase-{course_id}"}, headers=auth("teacher"))
        assert response.status_code == 200, response.text
    rows = client.get("/api/v1/enterprise/scores?student_id=21", headers=auth("teacher")).json()["data"]
    assert {row["study_stage"] for row in rows} == {"preparatory", "language", "overseas"}
    correction = {**body, "score": "88", "expected_version": 1, "correction_reason": "复核录入"}
    del correction["submission_key"]
    assert client.put(f"/api/v1/enterprise/scores/{saved['id']}", json=correction, headers=auth("teacher")).status_code == 200
    assert len(client.get(f"/api/v1/enterprise/scores/{saved['id']}/history", headers=auth("teacher")).json()["data"]) >= 1
    denied = {**body, "student_id": 22, "submission_key": "outside-course"}
    assert client.post("/api/v1/enterprise/scores", json=denied, headers=auth("other")).status_code == 422
    batch = {"request_id": str(uuid4()), "title": "全班语言考试", "deadline_type": "exam", "study_stage": "language", "deadline": "2026-12-01T10:00:00"}
    url = "/api/v1/student-admin/academic-deadlines/classes/1/batch"
    assert client.post(url, json=batch, headers=auth("other")).status_code == 404
    response = client.post(url, json=batch, headers=auth("teacher"))
    assert response.status_code == 201, response.text
    assert response.json()["data"]["student_count"] == 1
    assert client.post(url, json=batch, headers=auth("teacher")).json()["data"]["replayed"] is True
    assert client.post(url, json={**batch, "title": "不同内容"}, headers=auth("teacher")).status_code == 409
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(AcademicDeadline)) == 1
    student_view = client.get("/api/v1/student/deadlines?upcoming=false", headers=auth("101"))
    assert student_view.json()["data"]["items"][0]["study_stage"] == "language"


def test_transfer_moves_all_unfinished_and_preserves_history(teacher_world):
    client, engine = teacher_world
    now = utc_now()
    with Session(engine) as db:
        db.add_all([StudentAdminService(id=1, student_id=21, service_type="leave", reason="待审批", status="pending", approver_id=None, create_time=now, update_time=now),
                    StudentAdminService(id=2, student_id=21, service_type="leave", reason="已审批", status="approved", approver_id=30, create_time=now, update_time=now),
                    WellbeingCase(id=1, student_id=21, status="following", note="关怀", assigned_to=30, created_at=now),
                    WellbeingFollowup(case_id=1, actor_id=30, note="历史跟进", created_at=now)])
        db.execute(text("INSERT INTO student_psych_alert (id,student_id,teacher_id,status) VALUES (1,21,NULL,'pending'), (2,21,30,'closed')"))
        db.execute(student_feedback_ticket.insert(), [
            {"id": i, "student_id": 21, "category": cat, "ticket_type": "complaint", "content": "测试", "status": "processing", "priority": "medium", "assignee_id": owner, "is_notified": 0, "create_time": now, "update_time": now}
            for i, cat, owner in [(1, "learning", 30), (2, "company", 11)]])
        db.commit()
    url = "/api/v1/enterprise/classrooms/student-placements"
    body = {"student_id": 21, "project_id": 2, "class_id": 2, "expected_class_id": 1, "reason": "转班测试"}
    assert client.post(url, json=body, headers=auth("teacher")).status_code == 403
    response = client.post(url, json=body, headers=auth("admin"))
    assert response.status_code == 200, response.text
    assert client.post(url, json=body, headers=auth("admin")).status_code == 409
    assert client.get("/api/v1/teacher/students/21", headers=auth("teacher")).status_code == 403
    assert client.get("/api/v1/teacher/students/21", headers=auth("other")).status_code == 200
    with Session(engine) as db:
        assert db.get(StudentAdminService, 1).approver_id == 31
        assert db.get(StudentAdminService, 2).approver_id == 30
        assert db.get(WellbeingCase, 1).assigned_to == 31
        assert db.scalar(select(WellbeingFollowup.actor_id)) == 30
        assert db.execute(text("SELECT teacher_id FROM student_psych_alert ORDER BY id")).scalars().all() == [31, 30]
        assert dict(db.execute(select(student_feedback_ticket.c.id, student_feedback_ticket.c.assignee_id)).all()) == {1: 31, 2: 11}
        assert db.scalar(select(ClassPlacementHistory.actor_id)) == 10
        assert set(db.scalars(select(todo_item.c.assignee_id))) == {31}
    assert client.get('/api/v1/student-admin/psych-alerts?student_id=21', headers=auth('teacher')).status_code == 403
    follow = client.put('/api/v1/student-admin/psych-alerts/1', json={'status': 'following', 'follow_record': '新班主任已接手'}, headers=auth('other'))
    assert follow.status_code == 200 and '员工31' in follow.json()['data']['follow_record'], follow.text
    # Both account governance and role governance must enforce handover first.
    user = {"real_name": "人员31", "role_id": 5, "status": "disabled", "department": None, "contact_info": None}
    blocked = client.patch("/api/v1/auth/users/31", json=user, headers=auth("admin"))
    assert blocked.status_code == 409, blocked.text
    role = {"role_code": "team_leader", "role_name": "班主任", "status": 0, "permissions": list(ROLE_DEFAULTS["team_leader"])}
    assert client.put("/api/v1/auth/roles/5", json=role, headers=auth("admin")).status_code == 409
    moved = client.put("/api/v1/enterprise/classrooms/1", json={"name": "一班", "teacher_id": 31, "enabled": True}, headers=auth("admin"))
    assert moved.status_code == 200, moved.text
    assert client.patch("/api/v1/auth/users/30", json={**user, "real_name": "人员30"}, headers=auth("admin")).status_code == 200


def test_failed_transfer_rolls_back_roster_and_teacher(teacher_world, monkeypatch):
    from app.modules.classroom import service
    from app.modules.classroom.schemas import StudentPlacementWrite
    client, engine = teacher_world
    def fail(*args):
        raise RuntimeError("交接写入失败")
    monkeypatch.setattr(service, "_reassign", fail)
    with Session(engine) as db:
        body = StudentPlacementWrite(student_id=21, project_id=2, class_id=2, expected_class_id=1, reason="回滚测试")
        with pytest.raises(RuntimeError):
            service.assign_student(db, EmployeePrincipal(10, frozenset({"classes:manage"})), body)
        assert db.get(ClassEnrollment, 21).class_id == 1
        assert db.scalar(text("SELECT class_teacher_id FROM student_info WHERE user_id=21")) == 30
        assert db.scalar(select(func.count()).select_from(ClassPlacementHistory)) == 0


def test_batch_enrollment_and_conflict_are_atomic(teacher_world):
    client, engine = teacher_world
    path = '/api/v1/enterprise/classrooms/student-placements/batch'
    body = {"project_id": 2, "class_id": 2, "reason": "批量转班", "students": [
        {"student_id": 21, "expected_class_id": 1}, {"student_id": 22, "expected_class_id": 1}]}
    assert client.post(path, json=body, headers=auth('teacher')).status_code == 403
    assert client.post(path, json=body, headers=auth('admin')).status_code == 409
    with Session(engine) as db:
        assert db.get(ClassEnrollment, 21).class_id == 1
        assert db.scalar(text("SELECT class_teacher_id FROM student_info WHERE user_id=21")) == 30
        assert db.scalar(select(func.count()).select_from(ClassPlacementHistory)) == 0
    body['students'][1]['expected_class_id'] = 2
    result = client.post(path, json=body, headers=auth('admin'))
    assert result.status_code == 200 and result.json()['data']['student_count'] == 2, result.text
    with Session(engine) as db:
        assert db.get(ClassEnrollment, 21).class_id == 2
        assert db.scalar(select(func.count()).select_from(ClassPlacementHistory)) == 1


def test_leave_proof_ownership_and_complaint_rerouting(teacher_world):
    client, engine = teacher_world
    upload_url = "/api/v1/student/leaves/attachments"
    invalid = client.post(upload_url, files={"file": ("bad.png", b"not a picture", "image/png")}, headers=auth("101"))
    assert invalid.status_code == 422
    broken = b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aD1sAAAAASUVORK5CYII=')
    assert client.post(upload_url, files={"file": ("broken.png", broken, "image/png")}, headers=auth("101")).status_code == 422
    upload = client.post(upload_url, files={"file": ("证明.pdf", b"%PDF-1.4\nproof", "application/pdf")}, headers=auth("101"))
    assert upload.status_code == 201, upload.text
    body = {"leave_type": "sick", "start_time": "2026-12-01T10:00:00", "end_time": "2026-12-02T10:00:00", "reason": "病假", "attachment_id": upload.json()["data"]["id"]}
    assert client.post("/api/v1/student/leaves", json=body, headers=auth("102")).status_code == 422
    leave = client.post("/api/v1/student/leaves", json=body, headers=auth("101"))
    assert leave.status_code == 201, leave.text
    path = f"/api/v1/student-admin/leaves/{leave.json()['data']['id']}/attachment"
    proof = client.get(path, headers=auth("teacher"))
    assert proof.status_code == 200 and proof.content.startswith(b"%PDF-")
    assert client.get(path, headers=auth("other")).status_code == 404
    record_url = path.removesuffix('/attachment')
    assert client.get(record_url, headers=auth("teacher")).json()["data"]["reason"] == "病假"
    assert client.get(record_url, headers=auth("other")).status_code == 404
    complaint = client.post("/api/v1/student/complaints", json={"category": "learning", "content": "误选类别"}, headers=auth("101"))
    assert complaint.status_code == 201, complaint.text
    tid = complaint.json()["data"]["id"]
    routing = {"expected_status": "pending", "expected_category": "learning", "expected_assignee_id": 30, "category": "company", "reason": "类别纠正"}
    route = f"/api/v1/enterprise/ticket-routing/{tid}"
    assert client.put(route, json=routing, headers=auth("teacher")).status_code == 403
    result = client.put(route, json=routing, headers=auth("manager"))
    assert result.status_code == 200 and result.json()["data"]["assignee_id"] == 11, result.text
    assert client.put(route, json=routing, headers=auth("admin")).status_code == 409
    history = client.get(f"/api/v1/enterprise/tickets/{tid}/history", headers=auth("admin"))
    assert history.status_code == 200 and len(history.json()["data"]) == 1
    with Session(engine) as db:
        assert db.scalar(select(todo_item.c.assignee_id).where(todo_item.c.related_type == "student_feedback_ticket", todo_item.c.related_id == tid)) == 11



def test_wellbeing_week_scope_and_archives_follow_the_class_roster(teacher_world):
    from datetime import date, datetime
    from sqlalchemy import Column, Integer, MetaData, Table
    from app.modules.statistics.scheduled_repository import generated
    from app.modules.statistics.wellbeing_models import WellbeingCheckin, WellbeingConsent

    client, engine = teacher_world
    Table("report_generation", MetaData(), Column("id", Integer, primary_key=True),
          *(Column(col.name, col.type) for col in generated.c if col.name != "id")).create(engine)
    stamp = datetime(2026, 11, 10, 10)
    with Session(engine) as db:
        for uid in (23, 24, 25, 26, 27):
            db.execute(accounts.insert().values(
                id=uid, username=f"1390000{uid:04}", password_hash="unused", real_name=f"学生{uid}",
                role_id=6, user_type="student", status="disabled" if uid == 27 else "normal",
                create_time=stamp, update_time=stamp,
            ))
        # A legacy teacher assignment without an actual enrollment cannot widen the report scope.
        db.execute(text("INSERT INTO student_info (user_id, class_teacher_id) VALUES (23, 30)"))
        db.execute(text("INSERT INTO student_psych_alert (student_id, teacher_id, status, risk_level, create_time) "
                        "VALUES (21,30,'pending','low',:stamp),(22,31,'pending','high',:stamp),"
                        "(23,NULL,'pending','medium',:stamp),(27,30,'pending','high',:stamp)"),
                   {"stamp": stamp.isoformat(sep=" ")})
        for uid in range(21, 28):
            db.add(WellbeingConsent(student_id=uid, granted=uid != 26, version="v1", updated_at=stamp))
            db.add(WellbeingCheckin(student_id=uid, day=stamp.date(), emotion="good", stress="light", updated_at=stamp))
            db.execute(text("INSERT INTO student_psych_record (student_id,emotion_tag,emotion_score,record_date) "
                            "VALUES (:uid,'焦虑',65,:day)"), {"uid": uid, "day": stamp.date().isoformat()})
        db.execute(text("INSERT INTO student_psych_record (student_id,emotion_tag,emotion_score,record_date) "
                        "VALUES (21,'焦虑',65,'2026-11-10'),(21,'稀少标签',NULL,'2026-11-10'),"
                        "(21,'焦虑',65,'2026-11-01')"))
        db.commit()

    endpoint = "/api/v1/reporting/wellbeing"
    body = {"anchor": date(2026, 11, 11).isoformat()}
    def read(role):
        response = client.get(endpoint + "/week", headers=auth(role), params=body)
        assert response.status_code == 200, response.text
        return response.json()["data"]

    manager = read("manager")
    assert manager["eligible"] == 6 and manager["participants"] == 5
    assert manager["emotion"] == [{"day": "2026-11-10", "label": "good", "count": 5}]
    assert {item["risk_level"] for item in manager["items"]} == {"low", "medium", "high"}
    assert manager["emotion_tags"] == [{"label": "焦虑", "count": 6}]
    assert manager["emotion_scores"] == [{"label": "60–79", "count": 6}]
    assert manager["records_suppressed"] is False
    assert manager["alert_reasons"] == [{"label": "其他原因", "count": 3}]
    teacher = read("teacher")
    assert teacher["eligible"] == 1 and teacher["participants"] is None
    assert teacher["items"] == [{"status": "pending", "risk_level": "low", "count": 1}]
    assert teacher["records_suppressed"] and teacher["emotion_tags"] == teacher["emotion_scores"] == []
    assert read("other")["items"] == [{"status": "pending", "risk_level": "high", "count": 1}]
    assert read("admin")["eligible"] == manager["eligible"]
    assert client.get(endpoint + "/week", headers=auth("advisor"), params=body).status_code == 403
    assert client.get(endpoint + "/cases", headers=auth("manager")).status_code == 403
    assert client.post(endpoint + "/reports", headers=auth("manager"), json=body).status_code == 403

    response = client.post(endpoint + "/reports", headers=auth("teacher"), json=body)
    assert response.status_code == 201, response.text
    archive_id = response.json()["data"]["archive_id"]
    archives = "/api/v1/reporting/archive"
    assert client.get(archives, headers=auth("teacher")).json()["data"][0]["id"] == archive_id
    with Session(engine) as db:
        enrollment = db.get(ClassEnrollment, 21)
        enrollment.class_id = 2
        db.commit()
    assert read("teacher")["eligible"] == 0
    assert read("other")["eligible"] == 2
    assert read("manager")["eligible"] == 6
    assert client.get(archives, headers=auth("teacher")).json()["data"] == [
        {"id": archive_id, "unavailable": True},
    ]
    assert client.get(f"{archives}/{archive_id}/pdf", headers=auth("teacher")).status_code == 403
    assert client.post(f"{endpoint}/reports/{archive_id}/review", headers=auth("teacher"),
                       json={"suggestion": "存档范围已变化"}).status_code == 404
