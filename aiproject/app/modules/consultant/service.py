from sqlalchemy.orm import Session

from app.modules.consultant.errors import ConflictError
from app.modules.consultant.repository import ConsultantRepository
from app.modules.consultant.schemas import FollowUpCreate, LeadCreate, LeadListParams, LeadStatusUpdate, LeadUpdate

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "new": {"contacting", "lost"},
    "contacting": {"qualified", "signed", "lost"},
    "qualified": {"signed", "lost"},
    "signed": set(),
    "lost": set(),
}


class ConsultantService:
    def __init__(self, db: Session):
        self.repo = ConsultantRepository(db)

    def create_lead(self, payload: LeadCreate):
        if payload.owner_employee_id is None:
            raise ValueError("业务层必须提供可信负责人")
        return self.repo.create_lead(payload)

    def get_lead(self, lead_id: int):
        return self.repo.get_lead(lead_id)

    def list_leads(self, params: LeadListParams):
        return self.repo.list_leads(params)

    def update_lead(self, lead_id: int, payload: LeadUpdate):
        lead = self.repo.get_lead(lead_id)
        if not lead:
            raise ValueError("意向客户不存在")
        return self.repo.patch_lead_fields(lead, payload)

    def update_status(self, lead_id: int, payload: LeadStatusUpdate, operator_employee_id: int):
        lead = self.repo.lock_lead(lead_id)
        if not lead:
            raise ValueError("意向客户不存在")
        if lead.owner_employee_id != operator_employee_id:
            raise PermissionError("仅负责顾问可更新该客户状态")
        current = lead.status
        if payload.status not in ALLOWED_TRANSITIONS.get(current, set()):
            raise ConflictError(f"不允许从 {current} 变更为 {payload.status}")
        if payload.status == "lost" and not payload.lost_reason:
            raise ValueError("标记流失必须填写原因")
        return self.repo.set_lead_status(lead, payload.status, payload.lost_reason)

    def lead_detail(self, lead_id: int):
        lead = self.repo.get_lead(lead_id)
        if not lead:
            raise ValueError("意向客户不存在")
        follow_ups = self.repo.list_follow_ups(lead_id)
        return lead, follow_ups

    def follow_up_count(self, lead_id: int, employee_id: int):
        lead = self.repo.get_lead(lead_id)
        if lead is None or lead.owner_employee_id != employee_id:
            return None
        return {"customer_name": lead.customer_name, "total": self.repo.count_follow_ups(lead_id)}

    def add_follow_up(self, lead_id: int, payload: FollowUpCreate):
        lead = self.repo.get_lead(lead_id)
        if not lead:
            raise ValueError("意向客户不存在")
        return self.repo.add_follow_up(
            lead,
            payload.employee_id,
            payload.follow_type,
            payload.content,
            payload.next_plan,
        )
