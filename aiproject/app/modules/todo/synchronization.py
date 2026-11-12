"""Synchronize source state and ownership without committing the caller's transaction."""
from app.shared.utils.time_util import now_naive
from .sync_repository import SOURCES, SourceTodoRepository


def synchronize_source(db, source_type, source_id):
    repo = SourceTodoRepository(db)
    source = repo.source(source_type, source_id)
    old = repo.todo(source_type, source_id)
    _, owner_column, kind, title = SOURCES[source_type]
    valid = source is not None and (source_type != "student_admin_service" or source["service_type"] == "leave")
    owner = source[owner_column] if valid else None
    status = source["status"] if valid else "missing"
    marker = "unassigned" if valid and owner is None else status
    active = valid and owner is not None and status in ("pending", "processing")
    now = now_naive()
    if old is None:
        if not active:
            return False
        rid = repo.create(dict(assignee_id=owner, todo_type=kind, title=title, related_type=source_type, related_id=source_id, priority="medium", status="pending", due_time=now, assignment_version=1, source_status=marker, create_time=now, update_time=now))
        if rid is not None:
            return True
        old = repo.todo(source_type, source_id)
    values = {"source_status": marker}
    if active:
        reactivated = old["source_status"] in ("approved", "rejected", "cancelled", "resolved", "closed", "missing", "unassigned")
        if old["assignee_id"] != owner or reactivated:
            values.update(assignee_id=owner, status="pending", completed_time=None, due_time=now, assignment_version=old["assignment_version"] + 1)
    else:
        terminal = "done" if valid and status in ("approved", "rejected", "resolved", "closed") else "cancelled"
        if old["status"] != terminal:
            values.update(status=terminal, completed_time=now)
    changed = any(old[key] != value for key, value in values.items())
    if changed:
        values["update_time"] = now
        repo.update(old["id"], values)
    return False
