from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.security import EmployeePrincipal, require_employee
from app.core.database import get_db
from app.core.responses import http_fail as fail, success
from app.modules.consultant.errors import ConflictError
from app.modules.student_admin.schemas import LeaveApprove, LeaveOut
from app.modules.student_admin.service import StudentAdminServiceLayer

router = APIRouter(prefix="/api/v1/student-admin", tags=["企业助手-学生行政（共用表）"])


@router.get("/leaves/pending", summary="待审批请假 ENT-09")
def pending_leaves(
    approver_id: int | None = None,
    db: Session = Depends(get_db),
    principal: EmployeePrincipal = Depends(require_employee),
):
    if approver_id is not None and approver_id != principal.employee_id:
        return fail("无权查询他人审批列表", code=403)
    items = StudentAdminServiceLayer(db).pending_leaves(principal.employee_id)
    return success([LeaveOut.model_validate(x) for x in items])


@router.post("/leaves/{leave_id}/approve", summary="请假审批（写操作）ENT-09/12")
def approve_leave(
    leave_id: int,
    payload: LeaveApprove,
    db: Session = Depends(get_db),
    principal: EmployeePrincipal = Depends(require_employee),
):
    if payload.approver_id is None:
        payload = payload.model_copy(update={"approver_id": principal.employee_id})
    if payload.approver_id != principal.employee_id:
        return fail("审批人与当前员工身份不一致", code=403)
    try:
        row = StudentAdminServiceLayer(db).approve_leave(leave_id, payload)
    except PermissionError as e:
        return fail(str(e), code=403)
    except ConflictError as e:
        return fail(str(e), code=409)
    except ValueError as e:
        return fail(str(e), code=404)
    return success(LeaveOut.model_validate(row), "审批完成")
