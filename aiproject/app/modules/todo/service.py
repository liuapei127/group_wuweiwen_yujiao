from app.core.exceptions import BusinessError
from app.core.security.authorization import require_owned
from app.shared.utils.time_util import now_naive
from .repository import TodoRepository


def create_todo(body, db, p):
    if body.due_time and body.due_time.tzinfo is not None:
        raise BusinessError(422, "当前业务库使用本地时间，请提交不带时区的时间")
    now = now_naive()
    rid = TodoRepository(db).create(dict(**body.model_dump(), assignee_id=p.employee_id, todo_type="custom", status="pending", create_time=now, update_time=now))
    db.commit()
    return {"id": rid}


def list_todos(due_only, limit, db, p):
    return TodoRepository(db).list_todos(p.employee_id, due_only, now_naive(), limit)


def finish_todo(todo_id, body, db, p):
    repo = TodoRepository(db)
    old = require_owned(repo.get(todo_id), p.employee_id, "assignee_id")
    transitions = {"pending": {"in_progress", "done", "cancelled"}, "in_progress": {"done", "cancelled"}, "done": set(), "cancelled": set()}
    if old["status"] != body.expected_status or body.status not in transitions[old["status"]]:
        raise BusinessError(409, "待办状态冲突")
    now = now_naive()
    count = repo.update_status(todo_id, p.employee_id, body.expected_status, dict(status=body.status, completed_time=now if body.status == "done" else None, update_time=now))
    if count != 1:
        db.rollback()
        raise BusinessError(409, "待办已变化")
    db.commit()
    return {"id": todo_id, "status": body.status}


def notifications(limit, db, p):
    return TodoRepository(db).list_notifications(p.employee_id, limit)
