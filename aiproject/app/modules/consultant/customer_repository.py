from datetime import datetime

from sqlalchemy import delete, func, literal, or_, select
from sqlalchemy.orm import Session

from app.modules.profile.models import CustomerProfile, CustomerSource, VisitorMaterial
from app.modules.visitor.models import VisitorAccount

from .customer_models import CustomerIdentity, CustomerImportPreview
from .models import CrmLead, VisitorIntake

def list_customers(
    db: Session, advisor_id: int, *, missing_name: str,
    keyword: str | None, status: str | None, page: int, page_size: int,
) -> dict:
    lead_name = CrmLead.customer_name
    nickname = VisitorAccount.nickname
    if db.get_bind().dialect.name in {"mysql", "mariadb"}:
        lead_name = lead_name.collate("utf8mb4_unicode_ci")
        nickname = nickname.collate("utf8mb4_unicode_ci")
    name = func.coalesce(func.nullif(func.nullif(lead_name, missing_name), ""), func.nullif(nickname, ""), lead_name)
    filtered = (
        select(CrmLead.id, name.label("customer_name"), CrmLead.status, literal("lead").label("kind"))
        .outerjoin(VisitorIntake, VisitorIntake.crm_lead_id == CrmLead.id)
        .outerjoin(VisitorAccount, VisitorAccount.id == VisitorIntake.visitor_id)
        .where(CrmLead.owner_employee_id == advisor_id)
    )
    if keyword and (text := keyword.strip()):
        filtered = filtered.where(or_(name.contains(text, autoescape=True), nickname.contains(text, autoescape=True)))
    if status:
        filtered = filtered.where(CrmLead.status == status)
    total = db.scalar(select(func.count()).select_from(filtered.subquery()))
    items = db.execute(filtered.order_by(CrmLead.id.desc()).offset((page - 1) * page_size).limit(page_size)).mappings()
    return {"total": total, "page": page, "page_size": page_size, "items": [dict(row) for row in items]}


def case_for_lead(db: Session, lead_id: int) -> VisitorIntake | None:
    return db.scalar(select(VisitorIntake).where(VisitorIntake.crm_lead_id == lead_id))


def lead_for_visitor(db: Session, visitor_id: int, *, lock: bool = False) -> CrmLead | None:
    stmt = select(CrmLead).join(VisitorIntake, VisitorIntake.crm_lead_id == CrmLead.id).where(
        VisitorIntake.visitor_id == visitor_id, VisitorIntake.advisor_id == CrmLead.owner_employee_id,
    )
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def linked_leads(db: Session, visitor_ids: list[int]) -> dict[int, int]:
    rows = db.execute(select(VisitorIntake.visitor_id, VisitorIntake.crm_lead_id).where(
        VisitorIntake.visitor_id.in_(visitor_ids), VisitorIntake.crm_lead_id.is_not(None),
    ))
    return {visitor_id: lead_id for visitor_id, lead_id in rows}


def identity_by_phone(db: Session, mobile: str) -> CustomerIdentity | None:
    return db.scalar(select(CustomerIdentity).where(CustomerIdentity.verified_mobile == mobile))


def visitor_imports(db: Session, lead_id: int, visitor_id: int, limit: int = 5):
    stmt = select(CustomerSource.id, CustomerSource.file_name, CustomerSource.create_time).join(
        VisitorMaterial, VisitorMaterial.source_id == CustomerSource.id,
    ).where(CustomerSource.lead_id == lead_id, VisitorMaterial.visitor_id == visitor_id)
    return db.execute(stmt.order_by(CustomerSource.id.desc()).limit(limit)).mappings().all()


def newest_screening(db: Session, lead_id: int) -> CustomerProfile | None:
    return db.scalar(
        select(CustomerProfile).where(CustomerProfile.lead_id == lead_id).order_by(CustomerProfile.id.desc()).limit(1)
    )


def preview_for_update(db: Session, preview_id: str) -> CustomerImportPreview | None:
    return db.get(CustomerImportPreview, preview_id, with_for_update=True)


def clean_expired_previews(db: Session, now: datetime) -> None:
    db.execute(delete(CustomerImportPreview).where(CustomerImportPreview.expires_at <= now))
