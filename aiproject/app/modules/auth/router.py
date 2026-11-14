from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import get_db
from app.core.responses import success
from app.core.security import EmployeePrincipal, require_employee
from app.core.security.dependencies import bearer
from .schemas import Login, PasswordChange, PasswordReset, UserCreate, UserUpdate, RoleWrite, StudentScope
from .service import AuthService
from . import base_portal, service_identity
from .schemas import ServiceTokenRequest

router=APIRouter(prefix='/api/v1/auth',tags=['员工登录与RBAC'])

def service(db:Session=Depends(get_db)):
    return AuthService(db)

@router.get('/status')
def status(svc:AuthService=Depends(service)):
    return success(svc.status())

@router.post('/login')
def login(body:Login,request:Request,response:Response,svc:AuthService=Depends(service)):
    remote=request.client.host if request.client else 'unknown'
    if get_settings().employee_identity_mode != base_portal.MODE:
        response.headers['Cache-Control'] = 'no-store'
        return success(svc.login(body,remote))
    secure, _ = base_portal.check_browser(request, csrf=False)
    result, refresh = svc.login(body, remote, use_base=True)
    base_portal.put_cookies(response, secure, refresh)
    return success(result)


@router.post('/refresh')
def refresh(request: Request, response: Response, svc: AuthService = Depends(service)):
    if get_settings().employee_identity_mode != base_portal.MODE:
        raise HTTPException(503, "BASE 刷新未启用")
    secure, refresh_token = base_portal.check_browser(request, csrf=True)
    result, rotated = svc.refresh_base(refresh_token)
    base_portal.put_cookies(response, secure, rotated, rotate_csrf=False)
    return success(result)

@router.post('/service-token')
def service_token(body: ServiceTokenRequest, response: Response, db: Session = Depends(get_db)):
    if get_settings().employee_identity_mode != base_portal.MODE:
        raise HTTPException(503, "BASE 服务身份未启用")
    response.headers["Cache-Control"] = "no-store"
    return success(service_identity.issue(db, body.client_id, body.client_secret.get_secret_value(), body.audience))


@router.get('/me')
def me(svc:AuthService=Depends(service),p:EmployeePrincipal=Depends(require_employee)):
    return success(svc.me(p))

@router.post('/logout')
def logout(request: Request, response: Response, svc: AuthService = Depends(service),
           credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    if get_settings().employee_identity_mode == base_portal.MODE:
        secure, refresh = base_portal.check_browser(request, csrf=True)
        header = request.headers.get("authorization")
        token = None
        if header is not None:
            scheme, _, token = header.partition(" ")
            if scheme.lower() != "bearer" or not token:
                raise HTTPException(401, "登录凭据无效")
        result = svc.logout_base(token, refresh)
        base_portal.clear_cookies(response, secure)
        return success(result)
    return success(svc.logout(require_employee(request, svc.db, credentials)))

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
