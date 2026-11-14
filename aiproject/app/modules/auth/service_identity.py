"""Credentials and finite-lived sessions for non-user BASE clients."""
import hashlib
import re
from datetime import timedelta, timezone
from hmac import compare_digest
from secrets import token_urlsafe
from uuid import uuid4

import jwt
from sqlalchemy import DateTime, LargeBinary, String, column, delete, insert, or_, select, table, update
from sqlalchemy.exc import SQLAlchemyError

from app.core.exceptions import BusinessError
from app.core.security.base_jwt import (
    RESOURCE_AUDIENCES, SERVICE_TOKEN_USE, BaseTokenError, issue_service_token, verify_token,
)
from app.core.security.base_session import RETENTION
from app.core.security.credentials import utc_now

from .base_portal import keys

CLIENT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,63}")
SECRET = re.compile(r"[A-Za-z0-9_-]{43}")
TTL_SECONDS = 900

clients = table("auth_service_client", column("client_id", String), column("display_name", String),
                column("status", String), column("secret_hash", LargeBinary),
                column("previous_secret_hash", LargeBinary), column("previous_secret_expires_at", DateTime),
                column("create_time", DateTime), column("update_time", DateTime))
audiences = table("auth_service_client_audience", column("client_id", String), column("audience", String))
sessions = table("auth_service_session", column("id", String), column("client_id", String),
                 column("expires_at", DateTime), column("revoked_at", DateTime), column("create_time", DateTime))
kids = table("auth_service_session_kid", column("session_id", String), column("kid", String),
             column("first_issued_at", DateTime))


def _digest(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("ascii")).digest()


def _locked_client(db, client_id):
    return db.execute(select(clients).where(clients.c.client_id == client_id).with_for_update()).mappings().first()


def _invalid():
    return BusinessError(401, "服务身份凭据无效")


def _store_error():
    return BusinessError(503, "服务身份存储不可用")


def _allowed(db, client_id, audience):
    return audience in RESOURCE_AUDIENCES and db.scalar(select(audiences.c.audience).where(
        audiences.c.client_id == client_id, audiences.c.audience == audience,
    )) is not None


def authenticate_service(db, token: str, audience: str) -> str:
    config = keys()
    try:
        claims = verify_token(config, token, audience=audience, token_use=SERVICE_TOKEN_USE)
        client_id = claims["sub"][4:]
        now = utc_now()
        authenticated = db.scalar(select(sessions.c.id).join(
            clients, clients.c.client_id == sessions.c.client_id,
        ).where(
            sessions.c.id == claims["sid"], sessions.c.client_id == client_id,
            sessions.c.revoked_at.is_(None), sessions.c.expires_at > now, clients.c.status == "active",
        ))
        if authenticated is None or not _allowed(db, client_id, audience):
            raise _invalid()
        return client_id
    except BaseTokenError:
        raise _invalid() from None
    except SQLAlchemyError:
        db.rollback()
        raise _store_error() from None


def issue(db, client_id: str, secret: str, audience: str) -> dict:
    if not CLIENT_ID.fullmatch(client_id) or not SECRET.fullmatch(secret):
        raise _invalid()
    supplied = _digest(secret)
    config = keys()
    try:
        with db.begin():
            row = _locked_client(db, client_id)
            now = utc_now()
            active = row and compare_digest(row["secret_hash"], supplied)
            previous = (row and row["previous_secret_expires_at"] and row["previous_secret_expires_at"] > now
                        and compare_digest(row["previous_secret_hash"], supplied))
            if not row or row["status"] != "active" or not (active or previous) or not _allowed(db, client_id, audience):
                raise _invalid()
            sid = str(uuid4())
            token = issue_service_token(config, sub="svc:" + client_id, sid=sid, audience=audience,
                                        ttl_seconds=TTL_SECONDS, now=now.replace(tzinfo=timezone.utc))
            db.execute(insert(sessions).values(id=sid, client_id=client_id, create_time=now,
                                              expires_at=now + timedelta(seconds=TTL_SECONDS)))
            db.execute(insert(kids).values(session_id=sid, kid=jwt.get_unverified_header(token)["kid"],
                                          first_issued_at=now))
        return {"access_token": token, "token_type": "bearer", "expires_in": TTL_SECONDS}
    except SQLAlchemyError:
        raise _store_error() from None


def create(db, client_id: str, name: str, allowed: tuple[str, ...]) -> str:
    if not CLIENT_ID.fullmatch(client_id) or not allowed or set(allowed) - RESOURCE_AUDIENCES:
        raise BusinessError(422, "服务客户端或受众无效")
    secret = token_urlsafe(32)
    now = utc_now()
    with db.begin():
        db.execute(insert(clients).values(client_id=client_id, display_name=name, status="active",
                                          secret_hash=_digest(secret), create_time=now, update_time=now))
        db.execute(insert(audiences), [{"client_id": client_id, "audience": item} for item in sorted(set(allowed))])
    return secret


def rotate(db, client_id: str, grace_seconds: int = 0) -> str:
    if not 0 <= grace_seconds <= 3600:
        raise BusinessError(422, "旧凭证的有效期最多一小时")
    secret = token_urlsafe(32)
    with db.begin():
        row = _locked_client(db, client_id)
        if not row or row["status"] != "active":
            raise BusinessError(404, "服务客户端不可用")
        now = utc_now()
        db.execute(update(clients).where(clients.c.client_id == client_id).values(
            secret_hash=_digest(secret), update_time=now,
            previous_secret_hash=row["secret_hash"] if grace_seconds else None,
            previous_secret_expires_at=now + timedelta(seconds=grace_seconds) if grace_seconds else None,
        ))
    return secret


def disable(db, client_id: str) -> None:
    with db.begin():
        if _locked_client(db, client_id) is None:
            raise BusinessError(404, "服务客户端不存在")
        now = utc_now()
        db.execute(update(clients).where(clients.c.client_id == client_id).values(
            status="disabled", previous_secret_hash=None, previous_secret_expires_at=None, update_time=now,
        ))
        db.execute(update(sessions).where(
            sessions.c.client_id == client_id, sessions.c.revoked_at.is_(None),
        ).values(revoked_at=now))


def revoke_sessions_for_kid(db, kid: str) -> int:
    with db.begin():
        affected = select(kids.c.session_id).where(kids.c.kid == kid)
        result = db.execute(update(sessions).where(
            sessions.c.id.in_(affected), sessions.c.revoked_at.is_(None),
        ).values(revoked_at=utc_now()))
        return result.rowcount


def purge_expired_sessions(db) -> int:
    now = utc_now()
    cutoff = now - RETENTION
    with db.begin():
        db.execute(update(clients).where(clients.c.previous_secret_expires_at <= now).values(
            previous_secret_hash=None, previous_secret_expires_at=None,
        ))
        expired = list(db.scalars(select(sessions.c.id).where(
            or_(sessions.c.expires_at <= cutoff, sessions.c.revoked_at <= cutoff),
        ).with_for_update()))
        if not expired:
            return 0
        db.execute(delete(kids).where(kids.c.session_id.in_(expired)))
        result = db.execute(delete(sessions).where(sessions.c.id.in_(expired)))
        return result.rowcount
