from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.visitor.models import VisitorAccount

from .models import CrmLead, VisitorCall, VisitorIntake


def pending(db: Session, after_id: int, limit: int):
    query = (
        select(VisitorAccount.id.label("visitor_id"), VisitorAccount.created_at.label("registered_at"))
        .outerjoin(VisitorIntake, VisitorIntake.visitor_id == VisitorAccount.id)
        .where(VisitorIntake.visitor_id.is_(None), VisitorAccount.id > after_id)
        .order_by(VisitorAccount.id)
        .limit(limit)
    )
    return db.execute(query).mappings().all()


def assigned(db: Session, advisor_id: int, after_id: int, limit: int):
    query = (
        select(VisitorAccount, VisitorIntake)
        .join(VisitorIntake, VisitorIntake.visitor_id == VisitorAccount.id)
        .where(VisitorIntake.advisor_id == advisor_id, VisitorAccount.id > after_id)
        .order_by(VisitorAccount.id)
        .limit(limit)
    )
    return db.execute(query).all()


def lock_visitor(db: Session, visitor_id: int) -> VisitorAccount | None:
    return db.scalar(select(VisitorAccount).where(VisitorAccount.id == visitor_id).with_for_update())


def intake(db: Session, visitor_id: int, *, lock: bool) -> VisitorIntake | None:
    query = select(VisitorIntake).where(VisitorIntake.visitor_id == visitor_id)
    return db.scalar(query.with_for_update() if lock else query)


def call_by_request(db: Session, visitor_id: int, request_id: str) -> VisitorCall | None:
    return db.scalar(select(VisitorCall).where(
        VisitorCall.visitor_id == visitor_id, VisitorCall.request_id == request_id
    ).with_for_update())


def calls(db: Session, visitor_id: int, before_id: int | None, limit: int) -> list[VisitorCall]:
    query = select(VisitorCall).where(VisitorCall.visitor_id == visitor_id)
    if before_id is not None:
        query = query.where(VisitorCall.id < before_id)
    return list(db.scalars(query.order_by(VisitorCall.id.desc()).limit(limit)))


def call_history(db: Session, visitor_id: int):
    query = select(VisitorCall).where(VisitorCall.visitor_id == visitor_id).order_by(VisitorCall.id)
    return db.scalars(query).yield_per(100)


def lock_lead(db: Session, lead_id: int, employee_id: int) -> CrmLead | None:
    return db.scalar(select(CrmLead).where(
        CrmLead.id == lead_id, CrmLead.owner_employee_id == employee_id,
    ).with_for_update())
