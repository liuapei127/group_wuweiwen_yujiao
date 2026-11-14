from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import CustomerProfile, CustomerSource, SourceType, VisitorMaterial


def get_owned_source(
    db: Session, source_id: int, employee_id: int, *, for_update: bool = False
) -> CustomerSource | None:
    query = select(CustomerSource).where(
        CustomerSource.id == source_id, CustomerSource.operator_id == employee_id
    )
    if for_update:
        query = query.with_for_update()
    return db.scalar(query)


def latest_profile(db: Session, source_id: int, *, lock: bool = False) -> CustomerProfile | None:
    query = (
        select(CustomerProfile)
        .where(CustomerProfile.source_id == source_id)
        .order_by(CustomerProfile.id.desc())
        .limit(1)
    )
    return db.scalar(query.with_for_update() if lock else query)


def visitor_sources(
    db: Session, visitor_id: int, limit: int, *, source_id: int | None = None, before_id: int | None = None,
) -> list[CustomerSource]:
    query = (
        select(CustomerSource)
        .join(VisitorMaterial, VisitorMaterial.source_id == CustomerSource.id)
        .where(VisitorMaterial.visitor_id == visitor_id)
    )
    if source_id is not None:
        query = query.where(CustomerSource.id == source_id)
    if before_id is not None:
        query = query.where(CustomerSource.id < before_id)
    return list(db.scalars(query.order_by(CustomerSource.id.desc()).limit(limit)))


def latest_profiles(db: Session, source_ids: list[int]) -> dict[int, CustomerProfile]:
    if not source_ids:
        return {}
    ids = (
        select(func.max(CustomerProfile.id))
        .where(CustomerProfile.source_id.in_(source_ids))
        .group_by(CustomerProfile.source_id)
    )
    rows = db.scalars(select(CustomerProfile).where(CustomerProfile.id.in_(ids)))
    return {row.source_id: row for row in rows}


def visitor_source(db: Session, visitor_id: int, source_id: int, *, lock: bool = False):
    query = (
        select(CustomerSource)
        .join(VisitorMaterial, VisitorMaterial.source_id == CustomerSource.id)
        .where(VisitorMaterial.visitor_id == visitor_id, CustomerSource.id == source_id)
    )
    return db.scalar(query.with_for_update() if lock else query)


def visitor_attachment(db: Session, visitor_id: int, source_id: int) -> bytes | None:
    return db.scalar(select(VisitorMaterial.file_content).where(
        VisitorMaterial.visitor_id == visitor_id, VisitorMaterial.source_id == source_id
    ))


def advisor_sources(db: Session, employee_id: int, before_id: int | None, limit: int) -> list[CustomerSource]:
    query = select(CustomerSource).where(
        CustomerSource.operator_id == employee_id,
        CustomerSource.source_type != SourceType.manual,
        ~select(VisitorMaterial.source_id).where(VisitorMaterial.source_id == CustomerSource.id).exists(),
    )
    if before_id is not None:
        query = query.where(CustomerSource.id < before_id)
    return list(db.scalars(query.order_by(CustomerSource.id.desc()).limit(limit)))
