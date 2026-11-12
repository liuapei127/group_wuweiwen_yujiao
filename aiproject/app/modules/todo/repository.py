from sqlalchemy import select, insert, update
from .models import todo_item as todos, notification_log as notices

class TodoRepository:
    def __init__(self, db):
        self.db = db

    def create(self, values):
        return self.db.execute(insert(todos).values(**values)).inserted_primary_key[0]

    def list_todos(self, employee_id, due_only, now, limit):
        stmt = select(todos).where(todos.c.assignee_id == employee_id)
        if due_only:
            stmt = stmt.where(todos.c.status.in_(["pending", "in_progress"]), todos.c.due_time <= now)
        return [dict(row._mapping) for row in self.db.execute(stmt.order_by(todos.c.id.desc()).limit(limit))]

    def get(self, todo_id):
        row = self.db.execute(select(todos).where(todos.c.id == todo_id)).first()
        return dict(row._mapping) if row else None

    def update_status(self, todo_id, employee_id, expected_status, values):
        return self.db.execute(update(todos).where(todos.c.id == todo_id, todos.c.assignee_id == employee_id, todos.c.status == expected_status).values(**values)).rowcount

    def list_notifications(self, employee_id, limit):
        stmt = select(notices).where(notices.c.user_id == employee_id, notices.c.channel == "system").order_by(notices.c.id.desc()).limit(limit)
        return [dict(row._mapping) for row in self.db.execute(stmt)]
