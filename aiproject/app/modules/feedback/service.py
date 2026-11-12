from app.core.exceptions import BusinessError
from app.core.security.authorization import require_owned
from app.shared.utils.time_util import now_naive
from .repository import FeedbackRepository


def list_tickets(status, limit, db, p):
    return FeedbackRepository(db).list_tickets(p.employee_id, status, limit)


def ticket_detail(ticket_id, db, p):
    return require_owned(FeedbackRepository(db).get(ticket_id), p.employee_id, "assignee_id")


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
        from app.modules.todo.synchronization import synchronize_source
        synchronize_source(db, "student_feedback_ticket", ticket_id)
        db.commit()
        return {"id": ticket_id, "status": body.status, "is_notified": 0}
    except Exception:
        db.rollback()
        raise
