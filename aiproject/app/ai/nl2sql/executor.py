from datetime import date

from sqlalchemy.orm import Session

from app.modules.consultant.repository import ConsultantRepository
from app.modules.consultant.schemas import LeadListParams, LeadOut, FollowUpOut
from app.modules.employee_report.repository import EmployeeReportRepository
from app.modules.student_admin.repository import StudentAdminRepository
from app.ai.nl2sql.metadata import MAX_ROWS


class Nl2SqlExecutor:
    def __init__(self, db: Session):
        self.db = db
        self.consultant = ConsultantRepository(db)
        self.reports = EmployeeReportRepository(db)
        self.student_admin = StudentAdminRepository(db)

    def execute(self, intent: str, params: dict) -> dict:
        limit = min(int(params.get("_max_rows", MAX_ROWS)), MAX_ROWS)

        if intent == "lead_detail_by_name":
            lead = self.consultant.find_lead_by_name(str(params["customer_name"]), params["owner_employee_id"])
            if not lead:
                return {"rows": [], "message": "未找到客户"}
            follow_ups = self.consultant.list_follow_ups(lead.id, limit=limit)
            return {
                "lead": LeadOut.model_validate(lead).model_dump(),
                "follow_ups": [FollowUpOut.model_validate(x).model_dump() for x in follow_ups],
            }

        if intent == "lead_follow_ups_by_name":
            lead = self.consultant.find_lead_by_name(str(params["customer_name"]), params["owner_employee_id"])
            if not lead:
                return {"rows": [], "message": "未找到客户"}
            items = self.consultant.list_follow_ups(lead.id, limit=limit)
            return {"rows": [FollowUpOut.model_validate(x).model_dump() for x in items]}

        if intent == "leads_by_status":
            list_params = LeadListParams(
                status=params.get("status"),  # type: ignore[arg-type]
                owner_employee_id=params.get("owner_employee_id"),
                page=1,
                page_size=limit,
            )
            items, total = self.consultant.list_leads(list_params)
            return {
                "total": total,
                "rows": [LeadOut.model_validate(x).model_dump() for x in items],
            }

        if intent == "pending_leaves":
            items = self.student_admin.list_pending_leaves(params["approver_id"], limit=limit)
            return {
                "rows": [
                    {
                        "id": x.id,
                        "student_id": x.student_id,
                        "reason": x.reason,
                        "status": x.status,
                    }
                    for x in items
                ]
            }

        if intent == "daily_reports_recent":
            employee_id = params.get("employee_id")
            items = self.reports.list_reports(employee_id, date.today().replace(day=1), None, limit=limit)
            return {
                "rows": [
                    {
                        "employee_id": x.employee_id,
                        "report_date": str(x.report_date),
                        "content": x.content[:500],
                    }
                    for x in items
                ]
            }

        return {"rows": [], "message": "未实现"}
