
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.security import EmployeePrincipal, require_employee
from app.core.database import get_db
from app.core.responses import success
from app.modules.consultant.errors import ConflictError
from app.modules.consultant.schemas import (
    FollowUpCreate,
    FollowUpOut,
    LeadCreate,
    LeadDetailOut,
    LeadListParams,
    LeadOut,
    LeadStatus,
    LeadStatusUpdate,
    LeadUpdate,
)
from app.modules.consultant.service import ConsultantService
from app.modules.consultant.customer_service import list_managed_customers, save_legacy_lead

router = APIRouter(prefix="/api/v1/consultant", tags=["企业助手-意向客户"])


def _svc(db: Session = Depends(get_db)) -> ConsultantService:
    return ConsultantService(db)


@router.post("/leads", summary="意向客户录入 ENT-01")
def create_lead(
    payload: LeadCreate,
    svc: ConsultantService = Depends(_svc),
    principal: EmployeePrincipal = Depends(require_employee),
):
    if principal.role_code != "admin":
        raise HTTPException(status_code=403, detail="顾问只能补充已有客户档案")
    if payload.owner_employee_id is None:
        payload = payload.model_copy(update={"owner_employee_id": principal.employee_id})
    if payload.owner_employee_id != principal.employee_id:
        raise HTTPException(status_code=403, detail="仅可为本人名下录入客户")
    row = svc.create_lead(payload)
    return success(LeadOut.model_validate(row), "录入成功")


@router.get("/leads", summary="意向客户分页查询 ENT-02")
def list_leads(
    keyword: str | None = None,
    status: str | None = None,
    owner_employee_id: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    svc: ConsultantService = Depends(_svc),
    principal: EmployeePrincipal = Depends(require_employee),
):
    if owner_employee_id is not None and owner_employee_id != principal.employee_id:
        raise HTTPException(status_code=403, detail="无权查询他人客户列表")
    params = LeadListParams(
        keyword=keyword,
        status=status,  # type: ignore[arg-type]
        owner_employee_id=owner_employee_id or principal.employee_id,
        page=page,
        page_size=page_size,
    )
    items, total = svc.list_leads(params)
    return success(
        {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": [LeadOut.model_validate(x) for x in items],
        }
    )


@router.get("/customers", summary="我跟进的客户")
def list_customers(
    keyword: str | None = None,
    status: LeadStatus | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    principal: EmployeePrincipal = Depends(require_employee),
):
    return success(list_managed_customers(
        db, principal, keyword=keyword, status=status, page=page, page_size=page_size,
    ))


@router.get("/leads/{lead_id}", summary="客户详情含跟进 ENT-02")
def lead_detail(
    lead_id: int,
    svc: ConsultantService = Depends(_svc),
    principal: EmployeePrincipal = Depends(require_employee),
):
    try:
        lead, follow_ups = svc.lead_detail(lead_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="客户不存在") from None
    if lead.owner_employee_id != principal.employee_id:
        raise HTTPException(status_code=403, detail="无权查看该客户")
    return success(
        LeadDetailOut(
            lead=LeadOut.model_validate(lead),
            follow_ups=[FollowUpOut.model_validate(x) for x in follow_ups],
        )
    )


@router.patch("/leads/{lead_id}", summary="更新客户档案")
def patch_lead(
    lead_id: int,
    payload: LeadUpdate,
    svc: ConsultantService = Depends(_svc),
    principal: EmployeePrincipal = Depends(require_employee),
):
    lead = svc.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="客户不存在")
    if lead.owner_employee_id != principal.employee_id:
        raise HTTPException(status_code=403, detail="无权修改该客户")
    row = save_legacy_lead(svc.db, lead_id, principal, payload)
    return success(LeadOut.model_validate(row))


@router.patch("/leads/{lead_id}/status", summary="客户状态更新 ENT-03")
def patch_status(
    lead_id: int,
    payload: LeadStatusUpdate,
    svc: ConsultantService = Depends(_svc),
    principal: EmployeePrincipal = Depends(require_employee),
):
    try:
        row = svc.update_status(lead_id, payload, principal.employee_id)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ConflictError as e:
        raise HTTPException(status_code=409, detail=str(e)) from e
    except ValueError as e:
        if "不存在" in str(e):
            raise HTTPException(status_code=404, detail=str(e)) from e
        raise HTTPException(status_code=422, detail=str(e)) from e
    return success(LeadOut.model_validate(row), "状态已更新")


@router.get("/leads/{lead_id}/follow-ups/count", summary="统计本人客户跟进记录")
def follow_up_count(
    lead_id: int, svc: ConsultantService = Depends(_svc),
    principal: EmployeePrincipal = Depends(require_employee),
):
    data = svc.follow_up_count(lead_id, principal.employee_id)
    if data is None:
        raise HTTPException(404, "客户不存在")
    return success(data)


@router.post("/leads/{lead_id}/follow-ups", summary="新增跟进记录")
def create_follow_up(
    lead_id: int,
    payload: FollowUpCreate,
    svc: ConsultantService = Depends(_svc),
    principal: EmployeePrincipal = Depends(require_employee),
):
    lead = svc.get_lead(lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail="客户不存在")
    if lead.owner_employee_id != principal.employee_id:
        raise HTTPException(status_code=403, detail="无权跟进该客户")
    if payload.employee_id is None:
        payload = payload.model_copy(update={"employee_id": principal.employee_id})
    if payload.employee_id != principal.employee_id:
        raise HTTPException(status_code=403, detail="跟进人必须与当前登录员工一致")
    row = svc.add_follow_up(lead_id, payload)
    return success(FollowUpOut.model_validate(row), "跟进已保存")
