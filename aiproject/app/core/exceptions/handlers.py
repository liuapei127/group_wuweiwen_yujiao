from fastapi import Request
from fastapi.exception_handlers import request_validation_exception_handler
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from app.core.responses import fail
from . import BusinessError


async def business_error_handler(request: Request, exc: BusinessError):
    content = fail(exc.detail, exc.status_code) if exc.envelope else {"detail": exc.detail}
    return JSONResponse(status_code=exc.status_code, content=content)


async def validation_error_handler(request: Request, exc: RequestValidationError):
    route = request.scope.get("route")
    if request.method == "POST" and getattr(route, "path", None) in {
        "/api/v1/auth/users/{user_id}/password",
        "/api/v1/enterprise/website-accounts/{visitor_id}/password",
    }:
        errors = [{key: error[key] for key in ("type", "loc", "msg")} for error in exc.errors()]
        return JSONResponse(status_code=422, content={"detail": errors})
    return await request_validation_exception_handler(request, exc)
