from sqlalchemy import insert, or_, select, update
from .models import student_feedback_ticket as tickets

class FeedbackRepository:
    def __init__(self, db):
        self.db = db

    def list_tickets(self, employee_id, status, limit, *, all_complaints=False):
        visibility = tickets.c.assignee_id == employee_id
        if all_complaints:
            visibility = or_(visibility, tickets.c.ticket_type == "complaint")
        stmt = select(tickets).where(visibility)
        if status:
            stmt = stmt.where(tickets.c.status == status)
        return [dict(row._mapping) for row in self.db.execute(stmt.order_by(tickets.c.id.desc()).limit(limit))]

    def add_complaint(self, values):
        return self.db.execute(insert(tickets).values(**values)).inserted_primary_key[0]

    def list_student_complaints(self, student_id, before_id, limit):
        stmt = select(tickets).where(tickets.c.student_id == student_id, tickets.c.ticket_type == "complaint")
        if before_id is not None:
            stmt = stmt.where(tickets.c.id < before_id)
        return self.db.execute(stmt.order_by(tickets.c.id.desc()).limit(limit)).mappings().all()

    def get_student_complaint(self, student_id, ticket_id):
        stmt = select(tickets).where(
            tickets.c.id == ticket_id,
            tickets.c.student_id == student_id,
            tickets.c.ticket_type == "complaint",
        )
        return self.db.execute(stmt).mappings().one_or_none()

    def get(self, ticket_id):
        row = self.db.execute(select(tickets).where(tickets.c.id == ticket_id)).first()
        return dict(row._mapping) if row else None

    def update_status(self, ticket_id, employee_id, expected_status, values):
        return self.db.execute(update(tickets).where(tickets.c.id == ticket_id, tickets.c.assignee_id == employee_id, tickets.c.status == expected_status).values(**values)).rowcount
