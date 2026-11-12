from fastapi import FastAPI

from app.core.config import get_settings
from app.router_registry import register_routers
from app.model_registry import register_models

_mode = (get_settings().employee_identity_mode or "blocked").strip().lower()
if _mode == "insecure_header_repro":
    raise RuntimeError(
        "app.main 不允许 EMPLOYEE_IDENTITY_MODE=insecure_header_repro；"
        "漏洞复现请使用 tests.repro.asgi_app"
    )
if _mode not in ("blocked", "trusted_jwt"):
    raise RuntimeError(f"不支持的 EMPLOYEE_IDENTITY_MODE={_mode!r}")

register_models()

app = FastAPI(title="粤教教育服务后端")
register_routers(app)
