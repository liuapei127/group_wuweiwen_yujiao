"""BASE sessions and one-time refresh tokens. ENT login is not called."""
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
from sqlalchemy import delete, or_, select, update
from sqlalchemy.orm import Session

from app.core.security.base_identity import BaseIdentityError, resolve_identity
from app.core.security.base_jwt import (
    ACCESS_TOKEN_USE,
    MAX_TTL_SECONDS,
    BaseKeySet,
    issue_access_token,
    verify_token,
)
from app.core.security.base_session_schema import base_sessions, refresh_tokens, session_kids

REFRESH_TTL = timedelta(hours=12)
REFRESH_TTL_MAX = timedelta(days=14)
SESSION_TTL = timedelta(hours=12)
SESSION_TTL_MAX = timedelta(days=7)
IDLE_TTL = timedelta(hours=2)
IDLE_TTL_MAX = timedelta(hours=12)
RETENTION = timedelta(days=7)
TOUCH_GAP = timedelta(minutes=5)


class BaseSessionError(Exception):
    def __init__(self, code: str):
        if code not in {"invalid", "replay", "expired", "revoked", "denied"}:
            raise ValueError("unknown session error")
        self.code = code
        super().__init__("BASE 会话不可用")


@dataclass(frozen=True)
class IssuedLogin:
    access_token: str
    refresh_token: str
    session_id: str
    family_id: str


def start_session(
    db: Session,
    *,
    user_id: int,
    keyset: BaseKeySet,
    audience: str,
    now: datetime | None = None,
    refresh_ttl: timedelta = REFRESH_TTL,
    session_ttl: timedelta = SESSION_TTL,
) -> IssuedLogin:
    _check_windows(refresh_ttl, session_ttl, IDLE_TTL)
    moment = _naive(now)
    identity = _eligible(db, user_id)
    session_id = str(uuid4())
    family_id = str(uuid4())
    secret = _new_secret()
    expires = moment + session_ttl

    def work():
        db.execute(base_sessions.insert().values(
            id=session_id, user_id=identity.user_id, expires_at=expires, revoked_at=None,
            create_time=moment, last_used_at=moment, parent_session_id=None,
        ))
        _insert_refresh(db, secret, family_id, session_id, identity.user_id, min(moment + refresh_ttl, expires))
        access = _issue(db, identity, session_id, keyset, audience, moment, expires)
        return IssuedLogin(access, secret, session_id, family_id)

    return _transaction(db, work)


def refresh_session(
    db: Session,
    raw_token: str,
    *,
    keyset: BaseKeySet,
    audience: str,
    now: datetime | None = None,
    refresh_ttl: timedelta = REFRESH_TTL,
    idle_ttl: timedelta = IDLE_TTL,
) -> IssuedLogin:
    _check_windows(refresh_ttl, SESSION_TTL, idle_ttl)
    moment = _naive(now)
    digest = _hash(raw_token)
    box: dict = {}

    def work():
        _lock_refresh_row(db, digest)
        claimed = db.execute(
            update(refresh_tokens)
            .where(
                refresh_tokens.c.token_hash == digest,
                refresh_tokens.c.used_at.is_(None),
                refresh_tokens.c.revoked_at.is_(None),
            )
            .values(used_at=moment)
        )
        if claimed.rowcount != 1:
            row = _row_by_hash(db, digest)
            if row is None:
                box["error"] = "invalid"
                return
            if row["used_at"] is not None or row["revoked_at"] is not None:
                _revoke_family(db, row["family_id"], moment)
                _revoke_session_tree(db, row["session_id"], moment)
                box["error"] = "replay"
                return
            box["error"] = "invalid"
            return
        row = _row_by_hash(db, digest)
        failure = _rotation_block(db, row, moment, idle_ttl)
        if failure:
            _revoke_family(db, row["family_id"], moment)
            _revoke_session_tree(db, row["session_id"], moment)
            box["error"] = failure
            return
        secret = _new_secret()
        session_expires = _session(db, row["session_id"])["expires_at"]
        refresh_expires = min(moment + refresh_ttl, session_expires)
        db.execute(
            update(refresh_tokens)
            .where(refresh_tokens.c.token_hash == digest)
            .values(replaced_by=_hash(secret))
        )
        _insert_refresh(db, secret, row["family_id"], row["session_id"], row["user_id"], refresh_expires)
        _touch_last_used(db, row["session_id"], moment)
        identity = resolve_identity(db, int(row["user_id"]))
        access = _issue(db, identity, row["session_id"], keyset, audience, moment, session_expires)
        box["issued"] = IssuedLogin(access, secret, row["session_id"], row["family_id"])

    _transaction(db, work)
    if "error" in box:
        raise BaseSessionError(box["error"])
    return box["issued"]


def revoke_session(db: Session, session_id: str, *, now: datetime | None = None) -> None:
    moment = _naive(now)

    def work():
        if _session(db, session_id) is None:
            raise BaseSessionError("invalid")
        _revoke_session_tree(db, session_id, moment)
        for family_id in _families_for_sessions(db, _tree_ids(db, session_id)):
            _revoke_family(db, family_id, moment)

    try:
        _transaction(db, work)
    except BaseSessionError:
        raise


def revoke_all_sessions(db: Session, user_id: int, *, now: datetime | None = None) -> None:
    moment = _naive(now)

    def work():
        ids = list(db.execute(
            select(base_sessions.c.id).where(base_sessions.c.user_id == user_id)
        ).scalars())
        for session_id in ids:
            _revoke_session_tree(db, session_id, moment)
        for family_id in _families_for_user(db, user_id):
            _revoke_family(db, family_id, moment)

    _transaction(db, work)


def revoke_sessions_for_kid(db: Session, kid: str, *, now: datetime | None = None) -> None:
    moment = _naive(now)

    def work():
        ids = list(db.execute(
            select(session_kids.c.session_id).where(session_kids.c.kid == kid)
        ).scalars())
        for session_id in ids:
            _revoke_session_tree(db, session_id, moment)
            for family_id in _families_for_sessions(db, _tree_ids(db, session_id)):
                _revoke_family(db, family_id, moment)

    _transaction(db, work)


def require_live_session(db: Session, session_id: str, user_id: int, *, now: datetime | None = None):
    moment = _naive(now)
    row = _session(db, session_id)
    if row is None or int(row["user_id"]) != user_id:
        raise BaseSessionError("invalid")
    if row["revoked_at"] is not None:
        raise BaseSessionError("revoked")
    if row["expires_at"] <= moment:
        raise BaseSessionError("expired")
    return row


def access_matches_session(db: Session, token: str, *, keyset: BaseKeySet, audience: str, now: datetime | None = None):
    """Structural session check. It does not touch last_used_at and is not an HTTP route."""
    claims = verify_token(keyset, token, audience=audience, token_use=ACCESS_TOKEN_USE)
    require_live_session(db, claims["sid"], int(claims["sub"]), now=now)
    return claims


def note_verified_access(db: Session, token: str, *, keyset: BaseKeySet, audience: str, now: datetime | None = None):
    """Record a successful BASE access check. Not called by the ENT HS256 login path."""
    claims = verify_token(keyset, token, audience=audience, token_use=ACCESS_TOKEN_USE)
    moment = _naive(now)
    box: dict = {}

    def work():
        failure = _session_block(db, claims["sid"], int(claims["sub"]), moment, IDLE_TTL)
        if failure:
            if failure == "expired":
                for family_id in _families_for_sessions(db, _tree_ids(db, claims["sid"])):
                    _revoke_family(db, family_id, moment)
                _revoke_session_tree(db, claims["sid"], moment)
            box["error"] = failure
            return
        _touch_last_used(db, claims["sid"], moment)
        box["claims"] = claims

    _transaction(db, work)
    if "error" in box:
        raise BaseSessionError(box["error"])
    return box["claims"]


def purge_expired_families(db: Session, *, now: datetime | None = None) -> int:
    """Delete families that are entirely expired or revoked and past the fixed 7-day retention."""
    moment = _naive(now)
    box = {"count": 0}

    def work():
        family_ids = _purgeable_families(db, moment)
        if not family_ids:
            return
        session_ids = list(db.execute(
            select(refresh_tokens.c.session_id).where(refresh_tokens.c.family_id.in_(family_ids))
        ).scalars())
        db.execute(delete(refresh_tokens).where(refresh_tokens.c.family_id.in_(family_ids)))
        if session_ids:
            cutoff = moment - RETENTION
            db.execute(
                delete(base_sessions).where(
                    base_sessions.c.id.in_(session_ids),
                    ~base_sessions.c.id.in_(select(refresh_tokens.c.session_id)),
                    or_(
                        base_sessions.c.revoked_at <= cutoff,
                        base_sessions.c.expires_at <= cutoff,
                    ),
                )
            )
        box["count"] = len(family_ids)

    _transaction(db, work)
    return box["count"]


def _eligible(db, user_id: int):
    try:
        identity = resolve_identity(db, user_id)
    except BaseIdentityError as exc:
        raise BaseSessionError("denied") from None
    if not identity.ent_login_allowed:
        raise BaseSessionError("denied")
    return identity


def _touch_last_used(db, session_id: str, moment: datetime) -> None:
    cutoff = moment - TOUCH_GAP
    db.execute(
        update(base_sessions)
        .where(
            base_sessions.c.id == session_id,
            or_(
                base_sessions.c.last_used_at.is_(None),
                base_sessions.c.last_used_at <= cutoff,
            ),
        )
        .values(last_used_at=moment)
    )


def _session_block(db, session_id: str, user_id: int, moment: datetime, idle_ttl: timedelta) -> str | None:
    session = _session(db, session_id)
    if session is None or int(session["user_id"]) != user_id:
        return "invalid"
    if session["revoked_at"] is not None:
        return "revoked"
    if session["expires_at"] <= moment:
        return "expired"
    last_used = session["last_used_at"] or session["create_time"]
    if moment - last_used > idle_ttl:
        return "expired"
    return None


def _purgeable_families(db, moment: datetime) -> list[str]:
    cutoff = moment - RETENTION
    grouped: dict[str, list] = {}
    rows = db.execute(select(
        refresh_tokens.c.family_id,
        refresh_tokens.c.expires_at,
        refresh_tokens.c.used_at,
        refresh_tokens.c.revoked_at,
    )).mappings()
    for row in rows:
        grouped.setdefault(row["family_id"], []).append(row)
    return [
        family_id for family_id, items in grouped.items()
        if items and all(_row_past_retention(item, moment, cutoff) for item in items)
    ]


def _row_past_retention(row, moment: datetime, cutoff: datetime) -> bool:
    if row["used_at"] is None and row["revoked_at"] is None and row["expires_at"] > moment:
        return False
    if row["revoked_at"] is not None:
        return row["revoked_at"] <= cutoff
    if row["used_at"] is not None:
        return row["used_at"] <= cutoff
    return row["expires_at"] <= cutoff


def _rotation_block(db, row, moment, idle_ttl) -> str | None:
    if row["expires_at"] <= moment:
        return "expired"
    session = _session(db, row["session_id"])
    if session is None:
        return "invalid"
    if session["revoked_at"] is not None:
        return "revoked"
    if session["expires_at"] <= moment:
        return "expired"
    last_used = session["last_used_at"] or session["create_time"]
    if moment - last_used > idle_ttl:
        return "expired"
    try:
        identity = resolve_identity(db, int(row["user_id"]))
    except BaseIdentityError:
        return "denied"
    if not identity.ent_login_allowed or identity.user_id != int(row["user_id"]):
        return "denied"
    return None


def _issue(db, identity, session_id, keyset: BaseKeySet, audience, moment, session_expires) -> str:
    aware = moment.replace(tzinfo=timezone.utc)
    remaining = int((session_expires - moment).total_seconds())
    ttl = min(MAX_TTL_SECONDS, remaining)
    if ttl < 1:
        raise BaseSessionError("expired")
    token = issue_access_token(
        keyset, sub=identity.sub, sid=session_id, audience=audience,
        user_type=identity.user_type, ttl_seconds=ttl, now=aware,
    )
    _remember_kid(db, session_id, jwt.get_unverified_header(token)["kid"], moment)
    return token


def _remember_kid(db, session_id: str, kid: str, moment: datetime) -> None:
    found = db.execute(
        select(session_kids.c.kid).where(
            session_kids.c.session_id == session_id, session_kids.c.kid == kid,
        )
    ).first()
    if found is None:
        db.execute(session_kids.insert().values(
            session_id=session_id, kid=kid, first_issued_at=moment,
        ))


def _insert_refresh(db, secret, family_id, session_id, user_id, expires):
    db.execute(refresh_tokens.insert().values(
        token_hash=_hash(secret), family_id=family_id, session_id=session_id, user_id=user_id,
        expires_at=expires, used_at=None, revoked_at=None, replaced_by=None,
    ))


def _revoke_family(db, family_id: str, moment: datetime) -> None:
    db.execute(
        update(refresh_tokens)
        .where(refresh_tokens.c.family_id == family_id, refresh_tokens.c.revoked_at.is_(None))
        .values(revoked_at=moment)
    )


def _revoke_session_tree(db, session_id: str, moment: datetime) -> None:
    ids = _tree_ids(db, session_id)
    db.execute(
        update(base_sessions)
        .where(base_sessions.c.id.in_(ids), base_sessions.c.revoked_at.is_(None))
        .values(revoked_at=moment)
    )


def _tree_ids(db, session_id: str) -> list[str]:
    ids = [session_id]
    children = list(db.execute(
        select(base_sessions.c.id).where(base_sessions.c.parent_session_id == session_id)
    ).scalars())
    return ids + children


def _families_for_sessions(db, session_ids: list[str]) -> set[str]:
    if not session_ids:
        return set()
    return set(db.execute(
        select(refresh_tokens.c.family_id).where(refresh_tokens.c.session_id.in_(session_ids))
    ).scalars())


def _families_for_user(db, user_id: int) -> set[str]:
    return set(db.execute(
        select(refresh_tokens.c.family_id).where(refresh_tokens.c.user_id == user_id)
    ).scalars())


def _session(db, session_id: str):
    return db.execute(select(base_sessions).where(base_sessions.c.id == session_id)).mappings().first()


def _lock_refresh_row(db, digest: str) -> None:
    stmt = select(refresh_tokens.c.token_hash).where(refresh_tokens.c.token_hash == digest)
    bind = db.get_bind()
    if bind is not None and bind.dialect.name != "sqlite":
        stmt = stmt.with_for_update()
    db.execute(stmt).first()


def _row_by_hash(db, digest: str):
    return db.execute(
        select(refresh_tokens).where(refresh_tokens.c.token_hash == digest)
    ).mappings().first()


def _new_secret() -> str:
    return base64.urlsafe_b64encode(secrets.token_bytes(32)).decode("ascii").rstrip("=")


def _hash(secret: str) -> str:
    if not isinstance(secret, str) or secret == "":
        raise BaseSessionError("invalid")
    return hashlib.sha256(secret.encode("ascii")).hexdigest()


def _naive(now: datetime | None) -> datetime:
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is not None:
        moment = moment.astimezone(timezone.utc).replace(tzinfo=None)
    return moment


def _check_windows(refresh_ttl, session_ttl, idle_ttl) -> None:
    if refresh_ttl <= timedelta(0) or refresh_ttl > REFRESH_TTL_MAX:
        raise BaseSessionError("invalid")
    if session_ttl <= timedelta(0) or session_ttl > SESSION_TTL_MAX:
        raise BaseSessionError("invalid")
    if idle_ttl <= timedelta(0) or idle_ttl > IDLE_TTL_MAX:
        raise BaseSessionError("invalid")


def _transaction(db: Session, work):
    try:
        if not db.in_transaction():
            with db.begin():
                return work()
        result = work()
        db.commit()
        return result
    except Exception:
        if db.in_transaction():
            db.rollback()
        raise
