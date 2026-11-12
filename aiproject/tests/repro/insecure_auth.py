"""测试专用：历史 Bearer+员工头逻辑。仅供漏洞复现 ASGI，不得接入 app.main。"""

from fastapi import Header, HTTPException

from app.core.auth.dependencies import EmployeePrincipal
from app.core.config import get_settings


def require_employee_insecure(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_employee_id: int | None = Header(default=None, alias="X-Employee-Id"),
) -> EmployeePrincipal:
    settings = get_settings()
    expected = settings.auth_bearer_token
    if not expected:
        raise HTTPException(
            status_code=503,
            detail="认证服务未配置（AUTH_BEARER_TOKEN 未设置），业务接口暂不可用",
        )
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未认证")
    token = authorization.removeprefix("Bearer ").strip()
    if token != expected:
        raise HTTPException(status_code=401, detail="凭据无效")
    if x_employee_id is None or x_employee_id < 1:
        raise HTTPException(status_code=401, detail="缺少可信员工身份（X-Employee-Id）")
    return EmployeePrincipal(employee_id=x_employee_id)
