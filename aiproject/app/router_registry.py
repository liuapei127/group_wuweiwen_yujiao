from app.modules.portal.router import router as portal_router
from app.ai.assistant.router import router as assistant_router
from app.core.security.jwks_router import router as base_jwks_router
from app.modules.auth.router import router as auth_router
from app.modules.organization.router import router as organization_router
from app.modules.onboarding.router import router as onboarding_router
from app.modules.score.router import router as score_router
from app.modules.feedback.router import router as feedback_router
from app.modules.todo.router import router as todo_router
from fastapi import FastAPI
from app.core.exceptions import BusinessError
from app.core.exceptions.handlers import business_error_handler

from app.ai.nl2sql.router import router as nl2sql_router
from app.modules.consultant.router import router as consultant_router
from app.modules.employee_report.router import router as employee_report_router
from app.modules.enterprise_ops.router import router as enterprise_ops_router
from app.modules.student_admin.router import router as student_admin_router
from app.modules.system.router import router as system_router


def register_routers(app: FastAPI) -> None:
    app.add_exception_handler(BusinessError, business_error_handler)
    app.include_router(base_jwks_router)
    app.include_router(auth_router)
    app.include_router(portal_router)
    app.include_router(assistant_router)
    # 保留云端已有健康检查（无额外前缀）
    app.include_router(system_router)
    app.include_router(organization_router)
    app.include_router(onboarding_router)
    app.include_router(score_router)
    app.include_router(feedback_router)
    app.include_router(todo_router)
    # 企业智能助手（ENT）
    app.include_router(consultant_router)
    app.include_router(employee_report_router)
    app.include_router(student_admin_router)
    app.include_router(enterprise_ops_router)
    app.include_router(nl2sql_router)

