from datetime import datetime

from sqlalchemy import String, cast, delete, func, literal, select, type_coerce, union_all
from sqlalchemy.orm import Session

from app.modules.profile.models import CustomerProfile, CustomerSource, VisitorMaterial
from app.modules.visitor.models import VisitorAccount

from .customer_models import CustomerIdentity, CustomerImportPreview
from .models import CrmLead, VisitorIntake


def list_customers(
    db: Session, advisor_id: int, *, include_claimed: bool, missing_name: str,
    keyword: str | None, status: str | None, page: int, page_size: int,
) -> dict:
    lead_name = CrmLead.customer_name
    lead_status = type_coerce(CrmLead.status, String)
    pending_status = literal("pending_binding")
    # Existing CRM and website tables can have different MySQL collations.
    mysql = db.get_bind().dialect.name in {"mysql", "mariadb"}
    if mysql:
        lead_name = lead_name.collate("utf8mb4_unicode_ci")
        lead_status = lead_status.collate("utf8mb4_unicode_ci")
        pending_status = pending_status.collate("utf8mb4_unicode_ci")
    leads = select(
        CrmLead.id, lead_name.label("customer_name"), lead_status.label("status"),
        literal("lead").label("kind"),
    ).where(CrmLead.owner_employee_id == advisor_id)
    rows = leads
    if include_claimed:
        name = func.coalesce(
            func.nullif(func.nullif(VisitorAccount.name, missing_name), ""),
            func.nullif(VisitorAccount.nickname, ""),
            literal("游客 ") + cast(VisitorIntake.visitor_id, String),
        )
        if mysql:
            name = name.collate("utf8mb4_unicode_ci")
        pending = select(
            VisitorIntake.visitor_id.label("id"), name.label("customer_name"),
            pending_status.label("status"), literal("visitor").label("kind"),
        ).join(VisitorAccount, VisitorAccount.id == VisitorIntake.visitor_id).where(
            VisitorIntake.advisor_id == advisor_id, VisitorIntake.crm_lead_id.is_(None),
        )
        rows = union_all(leads, pending)
    customers = rows.subquery()
    filtered = select(customers)
    if keyword and keyword.strip():
        filtered = filtered.where(customers.c.customer_name.contains(keyword.strip(), autoescape=True))
    if status:
        filtered = filtered.where(customers.c.status == status)
    total = db.scalar(select(func.count()).select_from(filtered.subquery()))
    items = db.execute(
        filtered.order_by(customers.c.kind.desc(), customers.c.id.desc())
        .offset((page - 1) * page_size).limit(page_size)
    ).mappings()
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
