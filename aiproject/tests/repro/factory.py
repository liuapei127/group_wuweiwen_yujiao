"""独立 FastAPI 实例，不修改 app.main 单例。"""
from fastapi import FastAPI

from app.core.auth.dependencies import require_employee
from app.router_registry import register_routers
from tests.repro.insecure_auth import require_employee_insecure


def create_repro_app() -> FastAPI:
    application = FastAPI(title="repro-only-do-not-deploy")
    register_routers(application)
    application.dependency_overrides[require_employee] = require_employee_insecure
    return application
