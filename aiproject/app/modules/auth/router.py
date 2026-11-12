from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.responses import success
from app.core.security import EmployeePrincipal, require_employee
from .schemas import Login, PasswordChange, PasswordReset, UserCreate, UserUpdate, RoleWrite, StudentScope
from .service import AuthService

router=APIRouter(prefix='/api/v1/auth',tags=['员工登录与RBAC'])

def service(db:Session=Depends(get_db)):
    return AuthService(db)

@router.get('/status')
def status(svc:AuthService=Depends(service)):
    return success(svc.status())

@router.post('/login')
def login(body:Login,request:Request,svc:AuthService=Depends(service)):
    remote=request.client.host if request.client else 'unknown'
    return success(svc.login(body,remote))

@router.get('/me')
def me(svc:AuthService=Depends(service),p:EmployeePrincipal=Depends(require_employee)):
    return success(svc.me(p))

@router.post('/logout')
def logout(svc:AuthService=Depends(service),p:EmployeePrincipal=Depends(require_employee)):
    return success(svc.logout(p))

@router.post('/password')
def password(body:PasswordChange,svc:AuthService=Depends(service),p:EmployeePrincipal=Depends(require_employee)):
    return success(svc.change_password(body,p))

@router.get('/users')
def users(keyword:str='',page:int=Query(1,ge=1),page_size:int=Query(20,ge=1,le=100),
          svc:AuthService=Depends(service),p:EmployeePrincipal=Depends(require_employee)):
    return success(svc.users(keyword,page,page_size))

@router.post('/users')
def create_user(body:UserCreate,svc:AuthService=Depends(service),p:EmployeePrincipal=Depends(require_employee)):
    return success(svc.create_user(body,p))

@router.patch('/users/{user_id}')
def update_user(user_id:int,body:UserUpdate,svc:AuthService=Depends(service),p:EmployeePrincipal=Depends(require_employee)):
    return success(svc.update_user(user_id,body,p))

@router.post('/users/{user_id}/password')
def reset_password(user_id:int,body:PasswordReset,svc:AuthService=Depends(service),p:EmployeePrincipal=Depends(require_employee)):
    return success(svc.reset_password(user_id,body,p))

@router.put('/users/{user_id}/student-scope')
def scope(user_id:int,body:StudentScope,svc:AuthService=Depends(service),p:EmployeePrincipal=Depends(require_employee)):
    return success(svc.set_scope(user_id,body,p))

@router.get('/roles')
def roles(svc:AuthService=Depends(service),p:EmployeePrincipal=Depends(require_employee)):
    return success(svc.roles())

@router.post('/roles')
def create_role(body:RoleWrite,svc:AuthService=Depends(service),p:EmployeePrincipal=Depends(require_employee)):
    return success(svc.save_role(body,p))

@router.put('/roles/{role_id}')
def update_role(role_id:int,body:RoleWrite,svc:AuthService=Depends(service),p:EmployeePrincipal=Depends(require_employee)):
    return success(svc.save_role(body,p,role_id))

@router.get('/permissions')
def permissions(svc:AuthService=Depends(service),p:EmployeePrincipal=Depends(require_employee)):
    return success(svc.catalog())

@router.get('/students')
def students(svc:AuthService=Depends(service),p:EmployeePrincipal=Depends(require_employee)):
    return success(svc.students())

@router.get('/audit')
def audit(limit:int=Query(100,ge=1,le=500),svc:AuthService=Depends(service),p:EmployeePrincipal=Depends(require_employee)):
    return success(svc.audits(limit))
