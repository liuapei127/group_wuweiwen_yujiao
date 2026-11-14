from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.modules.auth.repository import AuthRepository
from app.modules.student_admin.repository import StudentAdminRepository
from app.modules.student.notifications import save_student_result
from app.modules.todo import synchronization
from .schemas import StudentComplaintCreate, StudentComplaintOut
from app.core.security.authorization import require_owned
from app.shared.utils.time_util import now_naive
from .repository import FeedbackRepository


def list_tickets(status, limit, db, p):
    return FeedbackRepository(db).list_tickets(
        p.employee_id, status, limit, all_complaints=_can_review_all_complaints(p)
    )


def ticket_detail(ticket_id, db, p):
    ticket = FeedbackRepository(db).get(ticket_id)
    if ticket and ticket["ticket_type"] == "complaint" and _can_review_all_complaints(p):
        return ticket
    return require_owned(ticket, p.employee_id, "assignee_id")


def _can_review_all_complaints(principal):
    return principal.role_code == "manager" and "tickets:read" in principal.permissions


def _company_assignee(db: Session) -> int | None:
    manager_id = get_settings().company_complaint_manager_id
    identity = AuthRepository(db)
    if manager_id is None:
        eligible = identity.eligible_employee_ids("manager", ("tickets:read", "tickets:write"))
        return eligible[0] if len(eligible) == 1 else None
    account = identity.account(user_id=manager_id)
    if (
        account
        and account["status"] == "normal"
        and account["user_type"] == "employee"
        and account["role_code"] == "manager"
        and account["role_status"] == 1
        and {"tickets:read", "tickets:write"} <= identity.permissions(account["role_id"])
    ):
        return manager_id
    return None


def submit_student_complaint(
    db: Session, student_id: int, payload: StudentComplaintCreate
) -> StudentComplaintOut:
    """提交人 ID 来自调用方的可信学生身份。"""
    student_repo = StudentAdminRepository(db)
    feedback = FeedbackRepository(db)
    try:
        if not student_repo.lock_student(student_id):
            raise BusinessError(403, "学生账号不可用")
        if payload.category == "learning":
            assignee = student_repo.class_teacher(student_id)
        else:
            assignee = _company_assignee(db)
        if assignee is None:
            raise BusinessError(409, "尚未配置可处理该投诉的负责人")
        now = now_naive()
        values = {
            **payload.model_dump(),
            "student_id": student_id,
            "status": "pending",
            "priority": "medium",
            "assignee_id": assignee,
            "is_notified": 0,
            "create_time": now,
            "update_time": now,
        }
        ticket_id = feedback.add_complaint(values)
        synchronization.synchronize_source(db, "student_feedback_ticket", ticket_id)
        raw = feedback.get(ticket_id)
        if raw is None or raw.get("student_id") != student_id:
            raise BusinessError(500, "投诉工单写入失败")
        result = StudentComplaintOut.model_validate(raw)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


def student_complaints(db: Session, student_id: int, before_id: int | None, limit: int) -> list[StudentComplaintOut]:
    return [StudentComplaintOut.model_validate(row) for row in
            FeedbackRepository(db).list_student_complaints(student_id, before_id, limit)]


def student_complaint(db: Session, student_id: int, ticket_id: int) -> StudentComplaintOut:
    ticket = FeedbackRepository(db).get_student_complaint(student_id, ticket_id)
    if ticket is None:
        raise BusinessError(404, "投诉工单不存在")
    return StudentComplaintOut.model_validate(ticket)


def process_ticket(ticket_id, body, db, p):
    repo = FeedbackRepository(db)
    old = require_owned(repo.get(ticket_id), p.employee_id, "assignee_id")
    transitions = {"pending": {"processing"}, "processing": {"resolved"}, "resolved": {"closed"}, "closed": set()}
    if old["status"] != body.expected_status or body.status not in transitions[old["status"]]:
        raise BusinessError(409, "工单状态冲突")
    solution = body.solution or old["solution"]
    if body.status in ("resolved", "closed") and not solution:
        raise BusinessError(422, "解决或关闭必须提供解决说明")
    try:
        count = repo.update_status(ticket_id, p.employee_id, body.expected_status, dict(status=body.status, solution=solution, is_notified=0, update_time=now_naive()))
        if count != 1:
            db.rollback()
            raise BusinessError(409, "工单已变化，请刷新")
        synchronization.synchronize_source(db, "student_feedback_ticket", ticket_id)
        if old["ticket_type"] == "complaint" and body.status == "resolved":
            save_student_result(db, old["student_id"], "student_feedback_ticket", ticket_id, body.status,
                                "投诉处理结果", "你的投诉已处理，请在投诉反馈中查看。")
        db.commit()
        return {"id": ticket_id, "status": body.status, "is_notified": 0}
    except Exception:
        db.rollback()
        raise
