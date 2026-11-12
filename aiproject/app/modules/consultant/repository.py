from sqlalchemy import func, or_, select
from app.modules.consultant.errors import ConflictError
from sqlalchemy.orm import Session

from app.modules.consultant.models import CrmFollowUp, CrmLead
from app.modules.consultant.schemas import LeadCreate, LeadListParams, LeadUpdate
from app.shared.utils.time_util import now_naive


class ConsultantRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_lead(self, payload: LeadCreate) -> CrmLead:
        now = now_naive()
        row = CrmLead(**payload.model_dump(), status="new", create_time=now, update_time=now)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def get_lead(self, lead_id: int) -> CrmLead | None:
        return self.db.get(CrmLead, lead_id)

    def list_leads(self, params: LeadListParams) -> tuple[list[CrmLead], int]:
        stmt = select(CrmLead)
        if params.status:
            stmt = stmt.where(CrmLead.status == params.status)
        if params.owner_employee_id:
            stmt = stmt.where(CrmLead.owner_employee_id == params.owner_employee_id)
        if params.keyword:
            like = f"%{params.keyword}%"
            stmt = stmt.where(
                or_(
                    CrmLead.customer_name.like(like),
                    CrmLead.contact_info.like(like),
                    CrmLead.intended_major.like(like),
                )
            )
        total = self.db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
        stmt = stmt.order_by(CrmLead.id.desc()).offset((params.page - 1) * params.page_size).limit(params.page_size)
        return list(self.db.scalars(stmt).all()), total

    def patch_lead_fields(self, lead: CrmLead, payload: LeadUpdate) -> CrmLead:
        for k, v in payload.model_dump(exclude_unset=True).items():
            setattr(lead, k, v)
        lead.update_time = now_naive()
        self.db.commit()
        self.db.refresh(lead)
        return lead

    def set_lead_status(self, lead: CrmLead, status: str, lost_reason: str | None) -> CrmLead:
        lead.status = status
        lead.lost_reason = lost_reason
        lead.update_time = now_naive()
        self.db.commit()
        self.db.refresh(lead)
        return lead

    def add_follow_up(self, lead: CrmLead, employee_id: int, follow_type: str | None, content: str, next_plan: str | None) -> CrmFollowUp:
        now = now_naive()
        row = CrmFollowUp(
            lead_id=lead.id,
            employee_id=employee_id,
            follow_type=follow_type,
            content=content,
            next_plan=next_plan,
            create_time=now,
        )
        lead.last_contact_time = now
        lead.update_time = now
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def list_follow_ups(self, lead_id: int, limit: int = 50) -> list[CrmFollowUp]:
        stmt = (
            select(CrmFollowUp)
            .where(CrmFollowUp.lead_id == lead_id)
            .order_by(CrmFollowUp.id.desc())
            .limit(limit)
        )
        return list(self.db.scalars(stmt).all())

    def find_lead_by_name(self, name: str, owner_employee_id: int) -> CrmLead | None:
        if not owner_employee_id:
            raise PermissionError("必须提供可信员工身份")
        stmt = select(CrmLead).where(
            CrmLead.customer_name == name,
            CrmLead.owner_employee_id == owner_employee_id,
        ).limit(2)
        rows = list(self.db.scalars(stmt).all())
        if len(rows) > 1:
            raise ConflictError("本人名下存在同名客户，请使用客户 ID")
        return rows[0] if rows else None
