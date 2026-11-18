import json
from sqlalchemy import insert, or_, select, update
from app.modules.auth.models import audit_log
from .models import student_feedback_ticket as tickets
from .access import visible_tickets

class FeedbackRepository:
    def __init__(self, db):
        self.db = db

    def list_tickets(self, principal, status, limit):
        stmt = select(tickets).where(visible_tickets(tickets.c, principal))
        if status:
            stmt = stmt.where(tickets.c.status == status)
        return [dict(row._mapping) for row in self.db.execute(stmt.order_by(tickets.c.id.desc()).limit(limit))]

    def add_complaint(self, values):
        return self.db.execute(insert(tickets).values(**values)).inserted_primary_key[0]

    def visible_ids(self, principal, ids):
        return set(self.db.scalars(select(tickets.c.id).where(tickets.c.id.in_(ids), visible_tickets(tickets.c, principal))))

    def list_student_complaints(self, student_id, before_id, limit):
        stmt = select(tickets).where(tickets.c.student_id == student_id, tickets.c.ticket_type.in_(("complaint", "suggestion")))
        if before_id is not None:
            stmt = stmt.where(tickets.c.id < before_id)
        return self.db.execute(stmt.order_by(tickets.c.id.desc()).limit(limit)).mappings().all()

    def get_student_complaint(self, student_id, ticket_id):
        stmt = select(tickets).where(
            tickets.c.id == ticket_id,
            tickets.c.student_id == student_id,
            tickets.c.ticket_type.in_(("complaint", "suggestion")),
        )
        return self.db.execute(stmt).mappings().one_or_none()

    def get(self, ticket_id, *, lock=False):
        stmt = select(tickets).where(tickets.c.id == ticket_id)
        row = self.db.execute(stmt.with_for_update() if lock else stmt).first()
        return dict(row._mapping) if row else None

    def routing_queue(self):
        return [dict(row) for row in self.db.execute(select(tickets).where(
            tickets.c.ticket_type.in_(("complaint", "suggestion")), tickets.c.status.in_(("pending", "processing")),
        ).order_by(tickets.c.id.desc()).limit(200)).mappings()]

    def history(self, ticket_id):
        rows = self.db.execute(select(audit_log).where(
            audit_log.c.action.in_(("ticket_processed", "ticket_routed")),
            audit_log.c.target == str(ticket_id),
        ).order_by(audit_log.c.id)).mappings()
        return [{"actor_id": row["actor_id"], "action": row["action"], "created_at": row["create_time"],
                 "details": json.loads(row["details"])} for row in rows]

    def update_status(self, ticket_id, employee_id, expected_status, values):
        return self.db.execute(update(tickets).where(tickets.c.id == ticket_id, tickets.c.assignee_id == employee_id, tickets.c.status == expected_status).values(**values)).rowcount
