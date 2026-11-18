import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.modules.auth.models import audit_log
from app.modules.student_admin.models import StudentAdminService, SysUser
from app.modules.student_admin.schemas import LeaveApprove, StudentLeaveCreate
from app.modules.student_admin.service import StudentAdminServiceLayer
from app.modules.todo import synchronization
from app.modules.todo.models import notification_log, todo_item


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for table in (SysUser.__table__, StudentAdminService.__table__, todo_item, notification_log, audit_log):
            table.create(conn)
        conn.execute(text("CREATE TABLE student_info (user_id INTEGER, class_teacher_id INTEGER)"))
        conn.execute(text("INSERT INTO student_info VALUES (1, 3)"))
    with Session(engine) as session:
        session.add_all([
            SysUser(id=1, real_name="学生甲", user_type="student"),
            SysUser(id=2, real_name="学生乙", user_type="student"),
            SysUser(id=3, real_name="班主任", user_type="employee"),
        ])
        session.commit()
        yield session
    engine.dispose()


def request(**changes):
    return StudentLeaveCreate.model_validate({
        "leave_type": "personal", "start_time": "2026-12-10T09:00:00",
        "end_time": "2026-12-10T11:00:00", "reason": "请假事由", **changes,
    })


def test_stu_submission_assigns_teacher_and_approval_is_visible_to_student(db):
    service = StudentAdminServiceLayer(db)
    leave = service.submit_student_leave(1, request())
    todo = db.execute(select(todo_item)).mappings().one()
    assert (leave.status, leave.approver_id) == ("pending", 3)
    assert (todo["assignee_id"], todo["related_id"], todo["status"]) == (3, leave.id, "pending")

    with pytest.raises(BusinessError) as duplicate:
        service.submit_student_leave(1, request(reason="改个原因还是同一时段"))
    assert duplicate.value.status_code == 409
    with pytest.raises(BusinessError) as unauthorized:
        service.student_leave(2, leave.id)
    assert unauthorized.value.status_code == 404
    with pytest.raises(PermissionError):
        service.approve_leave(leave.id, LeaveApprove(approver_id=4, decision="approved"))

    service.approve_leave_by_student_name(
        "学生甲", LeaveApprove(approver_id=3, decision="approved", approval_comment="同意")
    )
    updated = service.student_leave(1, leave.id)
    assert (updated.status, updated.approval_comment) == ("approved", "同意")
    assert db.scalar(select(todo_item.c.status)) == "done"
    with pytest.raises(BusinessError) as duplicate_after_approval:
        service.submit_student_leave(1, request())
    assert duplicate_after_approval.value.status_code == 409


def test_submit_requires_a_teacher_and_rolls_back_if_todo_fails(db, monkeypatch):
    service = StudentAdminServiceLayer(db)
    with pytest.raises(BusinessError) as unassigned:
        service.submit_student_leave(2, request())
    assert unassigned.value.status_code == 409

    def fail(*args):
        raise RuntimeError("todo unavailable")

    monkeypatch.setattr(synchronization, "synchronize_source", fail)
    with pytest.raises(RuntimeError, match="todo unavailable"):
        service.submit_student_leave(1, request())
    assert db.scalar(select(StudentAdminService.id)) is None
    assert db.scalar(select(todo_item.c.id)) is None


@pytest.mark.parametrize("changes", [
    {"approver_id": 3}, {"student_id": 2}, {"reason": "  "},
    {"end_time": "2026-12-10T08:59:00"}, {"start_time": "2026-12-10T09:00:00+08:00"},
    {"end_time": "2026-12-10T11:00:00.001"},
])
def test_student_leave_validates_input(changes):
    with pytest.raises(ValidationError):
        request(**changes)
