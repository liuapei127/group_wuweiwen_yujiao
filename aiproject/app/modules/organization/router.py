from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from typing import Literal
from app.core.security import EmployeePrincipal, require_employee
from app.core.database import get_db
from app.core.responses import success
from . import service

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

