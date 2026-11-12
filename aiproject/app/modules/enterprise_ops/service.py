from sqlalchemy.orm import Session

from app.core.security import EmployeePrincipal
from app.core.exceptions import CommandError
from app.modules.enterprise_ops.schemas import CommandResult
from app.modules.consultant.errors import ConflictError
from app.modules.consultant.repository import ConsultantRepository
from app.modules.consultant.schemas import LeadStatusUpdate
from app.modules.consultant.service import ConsultantService
from app.modules.enterprise_ops.schemas import CommandRequest
from app.modules.student_admin.schemas import LeaveApprove
from app.modules.student_admin.service import StudentAdminServiceLayer


def execute_command(body: CommandRequest, db: Session, principal: EmployeePrincipal):
    from app.core.security.authorization import require_permission
    target_permission={'update_lead_status_by_name':'crm:write','approve_leave_by_name':'leaves:approve'}.get(body.action)
    if target_permission: require_permission(principal,target_permission)
    actor_id = principal.employee_id
    try:
        if body.action == "update_lead_status_by_name":
            name = body.params.get("customer_name")
            status = body.params.get("status")
            if not name or not status:
                raise CommandError("需要 customer_name 与 status", code=400)
            repo = ConsultantRepository(db)
            lead = repo.find_lead_by_name(str(name), actor_id)
            if not lead:
                raise CommandError("客户不存在", code=404)
            row = ConsultantService(db).update_status(
                lead.id,
                LeadStatusUpdate(status=status, lost_reason=body.params.get("lost_reason")),
                actor_id,
            )
            return CommandResult({"lead_id": row.id, "status": row.status}, "状态已更新")

        if body.action == "approve_leave_by_name":
            name = body.params.get("student_name")
            decision = body.params.get("decision")
            approver_id = body.params.get("approver_id", actor_id)
            if type(approver_id) is not int:
                raise CommandError("approver_id 必须为整数", code=422)
            if approver_id != actor_id:
                raise CommandError("approver_id 与当前员工身份不一致", code=403)
            if not name or approver_id < 1:
                raise CommandError("需要 student_name 与 approver_id", code=400)
            if decision not in ("approved", "rejected"):
                raise CommandError("decision 非法", code=400)
            row = StudentAdminServiceLayer(db).approve_leave_by_student_name(
                str(name),
                LeaveApprove(approver_id=approver_id, decision=decision, approval_comment=body.params.get("approval_comment")),
            )
            return CommandResult({"leave_id": row.id, "status": row.status}, "审批完成")

        raise CommandError("未知 action", code=400)
    except PermissionError as e:
        raise CommandError(str(e), code=403)
    except ConflictError as e:
        raise CommandError(str(e), code=409)
    except ValueError:
        raise CommandError("参数不合法或目标不存在，请核对输入", code=422)
