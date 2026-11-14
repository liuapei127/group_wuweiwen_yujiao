from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.modules.visitor.models import VisitorAccount

from .models import EventLecture, EventRegistration


def event(db: Session, event_id: int, *, lock: bool) -> EventLecture | None:
    stmt = select(EventLecture).where(EventLecture.id == event_id)
    return db.scalar(stmt.with_for_update() if lock else stmt)


def upcoming(db: Session, now: datetime, offset: int, limit: int) -> list[EventLecture]:
    stmt = select(EventLecture).where(EventLecture.start_time > now, EventLecture.status == "upcoming", EventLecture.max_participants.is_not(None)).order_by(
        EventLecture.start_time, EventLecture.id
    ).offset(offset).limit(limit)
    return list(db.scalars(stmt))


def staff_events(db: Session, organizer_id: int | None, before_id: int | None, limit: int) -> list[EventLecture]:
    query = select(EventLecture)
    if organizer_id is not None:
        query = query.where(EventLecture.organizer_id == organizer_id)
    if before_id is not None:
        query = query.where(EventLecture.id < before_id)
    return list(db.scalars(query.order_by(EventLecture.id.desc()).limit(limit)))


def customer_bookings(db: Session, customer_id: int, event_ids: list[int]) -> dict[int, str]:
    rows = db.execute(select(EventRegistration.event_id, EventRegistration.status).where(
        EventRegistration.customer_id == customer_id, EventRegistration.event_id.in_(event_ids)
    ))
    return {event_id: status for event_id, status in rows}


def customer_reservations(
    db: Session, customer_id: int, before_id: int | None, limit: int,
) -> list[tuple[EventLecture, EventRegistration]]:
    stmt = select(EventLecture, EventRegistration).join(
        EventRegistration, EventRegistration.event_id == EventLecture.id
    ).where(EventRegistration.customer_id == customer_id)
    if before_id is not None:
        stmt = stmt.where(EventRegistration.id < before_id)
    return [(event, booking) for event, booking in db.execute(
        stmt.order_by(EventRegistration.id.desc()).limit(limit)
    )]


def reserve_seat(db: Session, event_id: int) -> bool:
    result = db.execute(update(EventLecture).where(
        EventLecture.id == event_id,
        EventLecture.current_participants < EventLecture.max_participants,
    ).values(current_participants=EventLecture.current_participants + 1))
    return result.rowcount == 1


def release_seat(db: Session, event_id: int) -> bool:
    result = db.execute(update(EventLecture).where(
        EventLecture.id == event_id, EventLecture.current_participants > 0
    ).values(current_participants=EventLecture.current_participants - 1))
    return result.rowcount == 1


def booking_for_customer(db: Session, event_id: int, customer_id: int) -> EventRegistration | None:
    return db.scalar(select(EventRegistration).where(
        EventRegistration.event_id == event_id, EventRegistration.customer_id == customer_id
    ).with_for_update())


def mark_cancelled(db: Session, event_id: int, customer_id: int, now) -> bool:
    result = db.execute(update(EventRegistration).where(
        EventRegistration.event_id == event_id, EventRegistration.customer_id == customer_id,
        EventRegistration.status == "registered",
    ).values(status="cancelled", cancelled_at=now))
    return result.rowcount == 1


def mark_attended(db: Session, event_id: int, registration_id: int, employee_id: int, now) -> bool:
    result = db.execute(update(EventRegistration).where(
        EventRegistration.id == registration_id, EventRegistration.event_id == event_id,
        EventRegistration.status == "registered",
    ).values(status="attended", attended_at=now, checked_in_by=employee_id))
    return result.rowcount == 1


def registrations(db: Session, event_id: int, after_id: int, limit: int):
    stmt = (select(EventRegistration, VisitorAccount.name)
            .outerjoin(VisitorAccount, VisitorAccount.id == EventRegistration.customer_id)
            .where(EventRegistration.event_id == event_id, EventRegistration.id > after_id)
            .order_by(EventRegistration.id).limit(limit))
    return db.execute(stmt).all()
