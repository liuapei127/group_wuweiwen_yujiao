import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.exceptions import BusinessError
from app.core.security import EmployeePrincipal
from app.modules.auth.models import role_permissions, roles
from app.modules.feedback import service
from app.modules.feedback.models import student_feedback_ticket
from app.modules.feedback.schemas import StudentComplaintCreate, TicketUpdate
from app.modules.todo.models import notification_log, todo_item


@pytest.fixture
def db(monkeypatch):
    settings = Settings(_env_file=None, company_complaint_manager_id=4)
    monkeypatch.setattr(service, "get_settings", lambda: settings)
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for table in (student_feedback_ticket, todo_item, notification_log, roles, role_permissions):
            table.create(conn)
        conn.execute(text("""CREATE TABLE sys_user (
            id INTEGER PRIMARY KEY, username TEXT, password_hash TEXT, real_name TEXT,
            user_type TEXT, role_id INTEGER, department TEXT, contact_info TEXT,
            avatar_url TEXT, status TEXT, create_time DATETIME, update_time DATETIME
        )"""))
        conn.execute(text("CREATE TABLE student_info (user_id INTEGER, class_teacher_id INTEGER)"))
        conn.execute(roles.insert().values(id=9, role_name="主管", role_code="manager"))
        conn.execute(role_permissions.insert(), [
            {"role_id": 9, "permission": "tickets:read"},
            {"role_id": 9, "permission": "tickets:write"},
        ])
        conn.execute(text("""INSERT INTO sys_user (id, real_name, user_type, status, role_id) VALUES
            (1, '学生甲', 'student', 'normal', NULL), (2, '学生乙', 'student', 'normal', NULL),
            (3, '班主任', 'employee', 'normal', NULL), (4, '主管', 'employee', 'normal', 9)
        """))
        conn.execute(text("INSERT INTO student_info VALUES (1, 3)"))
    with Session(engine) as session:
        yield session
    engine.dispose()


def complaint(category):
    return StudentComplaintCreate(category=category, content="投诉描述")


def test_complaint_routes_to_teacher_or_manager_and_updates_student_result(db, monkeypatch):
    monkeypatch.setattr(service, "get_settings", lambda: Settings(_env_file=None, company_complaint_manager_id=None))
    permissions = frozenset({"tickets:read", "tickets:write"})
    teacher = EmployeePrincipal(3, permissions, role_code="team_leader")
    manager = EmployeePrincipal(4, permissions, role_code="manager")
    learning = service.submit_student_complaint(db, 1, complaint("learning"))
    company = service.submit_student_complaint(db, 1, complaint("company"))
    assert {
        item["related_id"]: item["assignee_id"] for item in db.execute(select(todo_item)).mappings()
    } == {learning.id: 3, company.id: 4}
    assert {row["id"] for row in service.list_tickets(None, 10, db, manager)} == {learning.id, company.id}
    assert [row["id"] for row in service.list_tickets(None, 10, db, teacher)] == [learning.id]
    assert service.ticket_detail(learning.id, db, manager)["content"] == "投诉描述"

    start = TicketUpdate(expected_status="pending", status="processing")
    with pytest.raises(BusinessError) as unavailable:
        service.process_ticket(learning.id, start, db, manager)
    assert unavailable.value.status_code == 403
    with pytest.raises(BusinessError) as other:
        service.student_complaint(db, 2, company.id)
    assert other.value.status_code == 404

    service.process_ticket(company.id, start, db, manager)
    done = TicketUpdate(expected_status="processing", status="resolved", solution="已处理")
    result = service.process_ticket(company.id, done, db, manager)
    assert result["is_notified"] == 0
    assert service.student_complaint(db, 1, company.id).solution == "已处理"
    assert db.scalar(select(todo_item.c.status).where(todo_item.c.related_id == company.id)) == "done"


def test_unassigned_complaint_and_todo_failure_leave_no_records(db, monkeypatch):
    with pytest.raises(BusinessError) as no_teacher:
        service.submit_student_complaint(db, 2, complaint("learning"))
    assert no_teacher.value.status_code == 409

    monkeypatch.setattr(service, "get_settings", lambda: Settings(_env_file=None, company_complaint_manager_id=None))
    db.execute(text("INSERT INTO sys_user (id, real_name, user_type, status, role_id) VALUES (5, '另一位主管', 'employee', 'normal', 9)"))
    db.commit()
    with pytest.raises(BusinessError) as ambiguous_manager:
        service.submit_student_complaint(db, 1, complaint("company"))
    assert ambiguous_manager.value.status_code == 409
    db.execute(text("UPDATE sys_user SET status='disabled' WHERE id IN (4, 5)"))
    db.commit()
    with pytest.raises(BusinessError) as inactive_manager:
        service.submit_student_complaint(db, 1, complaint("company"))
    assert inactive_manager.value.status_code == 409

    def fail(*args):
        raise RuntimeError("写入待办失败")

    monkeypatch.setattr(service.synchronization, "synchronize_source", fail)
    with pytest.raises(RuntimeError):
        service.submit_student_complaint(db, 1, complaint("learning"))
    assert db.scalar(select(student_feedback_ticket.c.id)) is None
    assert db.scalar(select(todo_item.c.id)) is None
