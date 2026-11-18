from sqlalchemy import select, insert, update, and_, or_
from .models import todo_item as todos, notification_log as notices
from app.modules.feedback.access import visible_tickets
from app.modules.feedback.models import student_feedback_ticket as tickets
from app.modules.student_admin.models import StudentAdminService


def visible_todos(principal):
    """A stale assignment must not expose a source after handover or rerouting."""
    feedback = select(tickets.c.id).where(
        tickets.c.id == todos.c.related_id, visible_tickets(tickets.c, principal, assigned_only=True),
    ).exists()
    leave = select(StudentAdminService.id).where(
        StudentAdminService.id == todos.c.related_id,
        StudentAdminService.service_type == "leave",
        StudentAdminService.approver_id == principal.employee_id,
    ).exists()
    return and_(todos.c.assignee_id == principal.employee_id, or_(
        todos.c.related_type.is_(None),
        todos.c.related_type.not_in(("student_feedback_ticket", "student_admin_service")),
        and_(todos.c.related_type == "student_feedback_ticket", feedback),
        and_(todos.c.related_type == "student_admin_service", leave),
    ))


def visible_notifications(principal):
    source_todo = select(todos.c.id).where(todos.c.id == notices.c.related_id, visible_todos(principal)).exists()
    feedback = select(tickets.c.id).where(tickets.c.id == notices.c.related_id,
        visible_tickets(tickets.c, principal, assigned_only=True)).exists()
    leave = select(StudentAdminService.id).where(StudentAdminService.id == notices.c.related_id,
        StudentAdminService.service_type == "leave", StudentAdminService.approver_id == principal.employee_id).exists()
    return and_(notices.c.user_id == principal.employee_id, notices.c.channel == "system", or_(
        notices.c.related_type.is_(None),
        notices.c.related_type.not_in(("todo_item", "student_feedback_ticket", "student_admin_service")),
        and_(notices.c.related_type == "todo_item", source_todo),
        and_(notices.c.related_type == "student_feedback_ticket", feedback),
        and_(notices.c.related_type == "student_admin_service", leave),
    ))

class TodoRepository:
    def __init__(self, db):
        self.db = db

    def create(self, values):
        return self.db.execute(insert(todos).values(**values)).inserted_primary_key[0]

    def list_todos(self, principal, due_only, now, limit):
        stmt = select(todos).where(visible_todos(principal))
        if due_only:
            stmt = stmt.where(todos.c.status.in_(["pending", "in_progress"]), todos.c.due_time <= now)
        return [dict(row._mapping) for row in self.db.execute(stmt.order_by(todos.c.id.desc()).limit(limit))]

    def get(self, todo_id):
        row = self.db.execute(select(todos).where(todos.c.id == todo_id)).first()
        return dict(row._mapping) if row else None

    def update_status(self, todo_id, employee_id, expected_status, values):
        return self.db.execute(update(todos).where(todos.c.id == todo_id, todos.c.assignee_id == employee_id, todos.c.status == expected_status).values(**values)).rowcount

    def list_notifications(self, principal, limit):
        stmt = select(notices).where(visible_notifications(principal)).order_by(notices.c.id.desc()).limit(limit)
        return [dict(row._mapping) for row in self.db.execute(stmt)]
