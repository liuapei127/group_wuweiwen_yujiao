from fastapi import APIRouter, Depends, Path, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from typing import Annotated, Literal
from app.core.security import EmployeePrincipal, require_employee
from app.core.database import get_db
from app.core.responses import success
from . import membership, service
from .membership_schemas import MembershipWrite, OrganizationManagerWrite

router = APIRouter(prefix="/api/v1/enterprise", tags=["企业助手扩展功能"])

@router.get('/organizations')
def organizations(keyword: str='', limit: int=Query(50, ge=1, le=100), db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(jsonable_encoder(service.organizations(keyword=keyword, limit=limit, db=db, p=p)))

@router.get('/organizations/colleagues')
def colleagues(name: str=Query(min_length=1, max_length=64), db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(jsonable_encoder(service.colleagues(name=name, db=db, p=p)))

@router.get('/colleagues/{employee_id}/contact')
def colleague_contact(employee_id: int, db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(jsonable_encoder(service.colleague_contact(employee_id=employee_id, db=db, p=p)))



@router.get('/organizations/membership-options')
def membership_options(db: Session = Depends(get_db), p: EmployeePrincipal = Depends(require_employee)):
    return success(service.organizations("", 1000, db, p))


@router.get('/organizations/memberships/{user_id}')
def memberships(user_id: int, db: Session = Depends(get_db), p: EmployeePrincipal = Depends(require_employee)):
    return success(membership.list_memberships(db, user_id))


@router.put('/organizations/memberships/{user_id}/{org_id}')
def save_membership(user_id: int, org_id: int, payload: MembershipWrite, db: Session = Depends(get_db),
                    p: EmployeePrincipal = Depends(require_employee)):
    return success(membership.save_membership(db, user_id, org_id, payload, p.employee_id))


@router.get('/organizations/manager-options')
def manager_options(db: Session = Depends(get_db), p: EmployeePrincipal = Depends(require_employee)):
    return success(membership.manager_options(db))


@router.put('/organizations/{org_id}/manager')
def assign_manager(org_id: Annotated[int, Path(ge=1)], payload: OrganizationManagerWrite,
                   db: Session = Depends(get_db), p: EmployeePrincipal = Depends(require_employee)):
    return success(membership.assign_manager(db, org_id, payload.manager_id, p.employee_id))
