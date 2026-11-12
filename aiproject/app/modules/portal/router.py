from fastapi import APIRouter,Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import EmployeePrincipal,require_employee
from app.core.responses import success
from .service import PortalService
router=APIRouter(prefix='/api/v1/portal',tags=['ENT工作台'])

@router.get('/context')
def context(db:Session=Depends(get_db),p:EmployeePrincipal=Depends(require_employee)):
    return success(PortalService(db).context(p))

@router.get('/students')
def students(db:Session=Depends(get_db),p:EmployeePrincipal=Depends(require_employee)):
    return success(PortalService(db).students(p))

@router.get('/health')
def health(db:Session=Depends(get_db),p:EmployeePrincipal=Depends(require_employee)):
    return success(PortalService(db).health())
