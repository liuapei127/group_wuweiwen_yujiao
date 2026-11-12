from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.responses import fail
from . import BusinessError


async def business_error_handler(request: Request, exc: BusinessError):
    content = fail(exc.detail, exc.status_code) if exc.envelope else {"detail": exc.detail}
    return JSONResponse(status_code=exc.status_code, content=content)
