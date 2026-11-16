from app.modules.portal.router import router as portal_router
from app.ai.assistant.router import router as assistant_router
from app.core.security.jwks_router import router as base_jwks_router
from app.modules.auth.router import router as auth_router
from app.modules.organization.router import router as organization_router
from app.modules.onboarding.router import router as onboarding_router
from app.modules.score.router import router as score_router
from app.modules.feedback.router import router as feedback_router
from app.modules.events.router import router as events_router, visitor_router as visitor_events_router
from app.modules.visitor.content_router import public_router as website_content_router, staff_router as website_content_admin_router
from app.modules.visitor.router import router as visitor_auth_router, staff_router as website_accounts_router, course_router
from app.modules.student.router import (
    academic_router, alert_router, router as website_student_router, staff_router as staff_progress_router,
)
from app.modules.todo.router import router as todo_router
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from app.core.exceptions import BusinessError
from app.core.exceptions.handlers import business_error_handler, validation_error_handler

from app.ai.nl2sql.router import router as nl2sql_router
from app.modules.consultant.router import router as consultant_router
from app.modules.consultant.customer_router import admin_router as customer_admin_router, staff_router as customer_staff_router, visitor_router as customer_website_router
from app.modules.consultant.intake_router import router as visitor_intake_router
from app.modules.profile.router import router as profile_router, visitor_router as visitor_material_router
from app.modules.customer_service.router import router as customer_service_router
from app.modules.employee_report.router import router as employee_report_router
from app.modules.statistics.board_router import router as report_board_router
from app.modules.statistics.wellbeing_router import staff_router as wellbeing_staff_router, student_router as wellbeing_student_router
from app.modules.statistics.router import router as statistics_router
from app.modules.enterprise_ops.router import router as enterprise_ops_router
from app.modules.student_admin.router import router as student_admin_router
from app.modules.system.router import router as system_router


def register_routers(app: FastAPI) -> None:
    app.add_exception_handler(BusinessError, business_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
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
    app.include_router(events_router)
    app.include_router(visitor_auth_router)
    app.include_router(website_accounts_router)
    app.include_router(website_content_router)
    app.include_router(website_content_admin_router)
    app.include_router(course_router)
    app.include_router(website_student_router)
    app.include_router(staff_progress_router)
    app.include_router(academic_router)
    app.include_router(alert_router)
    app.include_router(visitor_events_router)
    app.include_router(todo_router)
    # 企业智能助手（ENT）
    app.include_router(consultant_router)
    app.include_router(customer_staff_router)
    app.include_router(customer_website_router)
    app.include_router(customer_admin_router)
    app.include_router(visitor_intake_router)
    app.include_router(profile_router)
    app.include_router(visitor_material_router)
    app.include_router(customer_service_router)
    app.include_router(employee_report_router)
    app.include_router(statistics_router)
    app.include_router(report_board_router)
    app.include_router(wellbeing_staff_router)
    app.include_router(wellbeing_student_router)
    app.include_router(student_admin_router)
    app.include_router(enterprise_ops_router)
    app.include_router(nl2sql_router)

