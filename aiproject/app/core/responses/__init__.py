from typing import Any


def success(data: Any = None, message: str = "ok") -> dict[str, Any]:
    return {"code": 0, "message": message, "data": data}


def fail(message: str, code: int = 1, data: Any = None) -> dict[str, Any]:
    return {"code": code, "message": message, "data": data}


def http_fail(message: str, code: int = 400, data: Any = None):
    """保留业务错误格式，同时返回真实 HTTP 错误状态。"""
    from fastapi.responses import JSONResponse
    return JSONResponse(status_code=code, content=fail(message, code, data))
