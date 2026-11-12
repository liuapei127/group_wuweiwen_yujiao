"""Source-first row locking; every caller owns the surrounding transaction."""
from sqlalchemy import select, insert, update
from sqlalchemy.exc import IntegrityError
from app.modules.student_admin.models import StudentAdminService
from app.modules.feedback.models import student_feedback_ticket
from .models import todo_item

SOURCES = {
    "student_admin_service": (StudentAdminService.__table__, "approver_id", "leave_approval", "待审批请假"),
    "student_feedback_ticket": (student_feedback_ticket, "assignee_id", "complaint_follow", "待处理投诉"),
}


class SourceTodoRepository:
    def __init__(self, db):
        self.db = db

    def source(self, source_type, source_id):
        table = SOURCES[source_type][0]
        row = self.db.execute(select(table).where(table.c.id == source_id).with_for_update()).mappings().first()
        return dict(row) if row else None

    def todo(self, source_type, source_id):
        row = self.db.execute(select(todo_item).where(todo_item.c.related_type == source_type, todo_item.c.related_id == source_id).with_for_update()).mappings().first()
        return dict(row) if row else None

    def create(self, values):
        if self.db.get_bind().dialect.name == "mysql":
            # MySQL deadlocks abort the entire transaction, including SAVEPOINTs.
            return self.db.execute(insert(todo_item).values(**values)).inserted_primary_key[0]
        try:
            with self.db.begin_nested():
                rid = self.db.execute(insert(todo_item).values(**values)).inserted_primary_key[0]
            return rid
        except IntegrityError:
            if self.todo(values["related_type"], values["related_id"]) is None:
                raise
            return None

    def update(self, todo_id, values):
        self.db.execute(update(todo_item).where(todo_item.c.id == todo_id).values(**values))
