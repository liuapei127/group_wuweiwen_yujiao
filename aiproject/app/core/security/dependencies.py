"""Employee identity is always server-verified; default deployment remains blocked."""
from dataclasses import dataclass
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.core.database import get_db

@dataclass(frozen=True)
class EmployeePrincipal:
    employee_id: int
    permissions: frozenset[str] = frozenset()
    student_ids: frozenset[int] = frozenset()
    username: str = ''
    role_code: str = ''
    session_id: str = ''

bearer=HTTPBearer(auto_error=False)

def require_employee(request:Request, db:Session=Depends(get_db),
                     credentials:HTTPAuthorizationCredentials|None=Depends(bearer)) -> EmployeePrincipal:
    mode=(get_settings().employee_identity_mode or 'blocked').strip().lower()
    if mode!='trusted_jwt':
        raise HTTPException(503,'员工可信身份未就绪，consultant 业务不可用')
    if not credentials or credentials.scheme.lower()!='bearer':
        raise HTTPException(401,'请先登录',headers={'WWW-Authenticate':'Bearer'})
    from app.modules.auth.service import AuthService
    from app.core.security.rbac import route_permission
    from app.core.security.authorization import require_permission
    principal=AuthService(db).authenticate(credentials.credentials)
    path=getattr(request.scope.get('route'),'path',request.url.path)
    permission=route_permission(request.method,path)
    if permission:require_permission(principal,permission)
    return principal
