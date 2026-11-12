from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from typing import Literal
from app.core.security import EmployeePrincipal, require_employee
from app.core.database import get_db
from app.core.responses import success
from . import service
from .schemas import GuideInput

router = APIRouter(prefix="/api/v1/enterprise", tags=["企业助手扩展功能"])

@router.get('/onboarding-guides')
def guides(keyword: str='', category: str | None=None, page: int=Query(1, ge=1), page_size: int=Query(20, ge=1, le=100), db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(jsonable_encoder(service.guides(keyword=keyword, category=category, page=page, page_size=page_size, db=db, p=p)))

@router.post('/onboarding-guides')
def create_guide(body: GuideInput, db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(jsonable_encoder(service.create_guide(body=body, db=db, p=p)))

