from sqlalchemy import select, update
from .models import student_feedback_ticket as tickets

class FeedbackRepository:
    def __init__(self, db):
        self.db = db

    def list_tickets(self, employee_id, status, limit):
        stmt = select(tickets).where(tickets.c.assignee_id == employee_id)
        if status:
            stmt = stmt.where(tickets.c.status == status)
        return [dict(row._mapping) for row in self.db.execute(stmt.order_by(tickets.c.id.desc()).limit(limit))]

    def get(self, ticket_id):
        row = self.db.execute(select(tickets).where(tickets.c.id == ticket_id)).first()
        return dict(row._mapping) if row else None

    def update_status(self, ticket_id, employee_id, expected_status, values):
        return self.db.execute(update(tickets).where(tickets.c.id == ticket_id, tickets.c.assignee_id == employee_id, tickets.c.status == expected_status).values(**values)).rowcount
