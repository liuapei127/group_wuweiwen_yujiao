"""Adapt the BASE session layer to the authenticated employee portal."""
import re
from datetime import datetime, timezone
from hmac import compare_digest
from secrets import token_urlsafe
from urllib.parse import urlsplit

from fastapi import HTTPException, Request, Response
from sqlalchemy import inspect

from app.core.config import get_settings
from app.core.security.base_identity import BaseIdentityError
from app.core.security.base_jwt import BaseKeyConfigError, BaseTokenError, load_keyset
from app.core.security.base_session import BaseSessionError, BaseSessionUnavailable, REFRESH_TTL
from app.core.security.base_session_schema import base_sessions, refresh_tokens, session_kids

MODE = "base_rs256"
AUDIENCE = "edu-api:ent"
_COOKIE_PATH = "/api/v1/auth"
_OPAQUE = re.compile(r"[A-Za-z0-9_-]{43}")


def portal_origin() -> tuple[str, bool]:
    settings = get_settings()
    origin = settings.base_portal_origin
    try:
        parsed = urlsplit(origin)
    except ValueError:
        raise HTTPException(503, "BASE 门户来源未配置") from None
    if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username is not None
            or parsed.path or parsed.query or parsed.fragment or parsed.netloc != parsed.netloc.lower()):
        raise HTTPException(503, "BASE 门户来源未配置")
    secure = not settings.base_local_insecure_cookies
    if parsed.scheme != "https" or not secure:
        if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost", "::1") or secure:
            raise HTTPException(503, "BASE 门户需要 HTTPS 或本机环回配置")
    return origin, secure


def _cookie_names(secure: bool) -> tuple[str, str]:
    return ("__Secure-edu_refresh", "__Host-edu_csrf") if secure else ("edu_local_refresh", "edu_local_csrf")


def check_browser(request: Request, *, csrf: bool) -> tuple[bool, str | None]:
    origin, secure = portal_origin()
    if request.headers.get("origin") != origin:
        raise HTTPException(403, "请求来源未获授权")
    if not secure and request.url.hostname not in ("127.0.0.1", "localhost", "::1"):
        raise HTTPException(403, "仅本机允许此登录配置")
    refresh_name, csrf_name = _cookie_names(secure)
    if csrf:
        cookie = request.cookies.get(csrf_name, "")
        supplied = request.headers.get("x-csrf-token", "")
        if not (_OPAQUE.fullmatch(cookie) and _OPAQUE.fullmatch(supplied) and compare_digest(cookie, supplied)):
            raise HTTPException(403, "CSRF 校验未通过")
    refresh = request.cookies.get(refresh_name, "")
    return secure, refresh if _OPAQUE.fullmatch(refresh) else None


def put_cookies(response: Response, secure: bool, refresh: str, *, rotate_csrf: bool = True) -> None:
    refresh_name, csrf_name = _cookie_names(secure)
    lifetime = int(REFRESH_TTL.total_seconds())
    response.headers["Cache-Control"] = "no-store"
    response.set_cookie(refresh_name, refresh, max_age=lifetime, secure=secure, httponly=True,
                        samesite="strict", path=_COOKIE_PATH)
    if rotate_csrf:
        response.set_cookie(csrf_name, token_urlsafe(32), max_age=lifetime, secure=secure, samesite="strict", path="/")


def clear_cookies(response: Response, secure: bool) -> None:
    refresh_name, csrf_name = _cookie_names(secure)
    response.headers["Cache-Control"] = "no-store"
    response.delete_cookie(refresh_name, path=_COOKIE_PATH, secure=secure, httponly=True, samesite="strict")
    response.delete_cookie(csrf_name, path="/", secure=secure, samesite="strict")


def keys():
    try:
        config = load_keyset()
        config.signing_key()
        return config
    except BaseKeyConfigError:
        raise HTTPException(503, "BASE 签发密钥未配置") from None


def map_failure(exc: Exception) -> HTTPException:
    if isinstance(exc, BaseSessionUnavailable):
        return HTTPException(503, "BASE 会话存储不可用")
    if isinstance(exc, BaseSessionError) and exc.code == "denied":
        return HTTPException(403, "当前账号无访问权限")
    return HTTPException(401, "登录已失效，请重新登录", headers={"WWW-Authenticate": "Bearer"})


SESSION_ERRORS = (BaseSessionError, BaseSessionUnavailable, BaseTokenError, BaseIdentityError)


def store_ready(db) -> bool:
    inspector = inspect(db.connection())
    return (inspector.has_table(refresh_tokens.name) and inspector.has_table(session_kids.name)
            and {"last_used_at", "parent_session_id"} <= {col["name"] for col in inspector.get_columns(base_sessions.name)})


def access_payload(token: str, expires: int, user: dict | None = None) -> dict:
    payload = {"access_token": token, "token_type": "bearer",
               "expires_at": datetime.fromtimestamp(expires, timezone.utc).isoformat().replace("+00:00", "Z")}
    if user is not None:
        payload["user"] = user
    return payload
