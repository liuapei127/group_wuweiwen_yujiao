"""BASE sessions and refresh rotation. Isolated SQLite only; no production writes."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import create_engine, insert, select, text, update
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.database import engine as production_engine
from app.core.security.base_jwt import ACCESS_TOKEN_USE, verify_token
from app.core.security.base_jwt import BaseTokenError
from app.core.security.base_session import (
    BaseSessionError,
    access_matches_session,
    refresh_session,
    revoke_all_sessions,
    revoke_session,
    revoke_sessions_for_kid,
    start_session,
)
from app.core.security.base_session_schema import (
    base_sessions,
    metadata,
    refresh_tokens,
    session_kids,
)
from app.core.security.base_jwt import keyset_from_config
from app.modules.auth.models import accounts, role_permissions, roles

NOW = datetime.now(timezone.utc).replace(tzinfo=None, microsecond=0)
AUD = "edu-api:ent"


def _pair():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption(),
    ).decode()
    public_pem = key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def _keyset(private_pem, public_pem, kid="base-current"):
    return keyset_from_config([{
        "kid": kid, "status": "active", "public_pem": public_pem, "private_pem": private_pem,
    }])


def _prepare(engine):
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE sys_user (
                id INTEGER PRIMARY KEY,
                username VARCHAR(64) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                real_name VARCHAR(64) NOT NULL,
                user_type VARCHAR(16) NOT NULL,
                role_id INTEGER,
                department VARCHAR(128),
                contact_info VARCHAR(128),
                avatar_url VARCHAR(512),
                status VARCHAR(16) NOT NULL,
                create_time DATETIME,
                update_time DATETIME
            )
            """
        ))
    roles.create(engine)
    role_permissions.create(engine)
    metadata.create_all(engine)


def _seed(db, user_id, username, user_type, role_id, role_code, *, status="normal", role_status=1):
    if db.execute(select(roles.c.id).where(roles.c.id == role_id)).first() is None:
        db.execute(insert(roles).values(id=role_id, role_code=role_code, role_name=role_code, status=role_status))
    db.execute(insert(accounts).values(
        id=user_id, username=username, password_hash="not-the-refresh-secret", real_name=username,
        user_type=user_type, role_id=role_id, status=status,
    ))
    db.commit()


@pytest.fixture()
def env(monkeypatch, tmp_path):
    def forbidden(*args, **kwargs):
        raise AssertionError("session test attempted production database access")
    monkeypatch.setattr(production_engine, "connect", forbidden)
    engine = create_engine(
        f"sqlite:///{tmp_path/'session.db'}",
        connect_args={"timeout": 10},
        poolclass=NullPool,
    )
    _prepare(engine)
    private_pem, public_pem = _pair()
    keyset = _keyset(private_pem, public_pem)
    db = Session(engine)
    _seed(db, 10, "employee.session", "employee", 1, "employee")
    try:
        yield db, engine, keyset, private_pem
    finally:
        db.close()
        engine.dispose()


def _hashes(db):
    return set(db.execute(select(refresh_tokens.c.token_hash)).scalars())


def test_refresh_secret_is_256_bits(monkeypatch):
    seen = {}

    def fake(n):
        seen["n"] = n
        return b"\x02" * n

    monkeypatch.setattr("app.core.security.base_session.secrets.token_bytes", fake)
    from app.core.security.base_session import _hash, _new_secret
    secret = _new_secret()
    assert seen["n"] == 32
    assert _hash(secret) != secret
    assert secret.count(".") != 2


def test_refresh_is_random_hashed_and_rotates(env):
    db, _engine, keyset, _private = env
    issued = start_session(db, user_id=10, keyset=keyset, audience=AUD, now=NOW)
    assert issued.refresh_token.count(".") != 2
    assert issued.refresh_token not in _hashes(db)
    stored = db.execute(select(refresh_tokens)).mappings().one()
    assert stored["token_hash"] != issued.refresh_token
    assert len(stored["token_hash"]) == 64
    second = refresh_session(db, issued.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=5))
    old = db.execute(select(refresh_tokens).where(refresh_tokens.c.token_hash == stored["token_hash"])).mappings().one()
    assert old["used_at"] is not None
    assert old["replaced_by"] != issued.refresh_token
    assert second.refresh_token not in _hashes(db)
    assert second.refresh_token != issued.refresh_token
    with pytest.raises(BaseSessionError) as replay:
        refresh_session(db, issued.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=6))
    assert replay.value.code == "replay"
    with pytest.raises(BaseSessionError):
        refresh_session(db, second.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=7))
    with pytest.raises(BaseSessionError) as missing:
        refresh_session(db, "missing-token", keyset=keyset, audience=AUD, now=NOW)
    assert missing.value.code == "invalid"


def test_expired_refresh_and_session_are_rejected(env):
    db, _engine, keyset, _private = env
    issued = start_session(
        db, user_id=10, keyset=keyset, audience=AUD, now=NOW, refresh_ttl=timedelta(minutes=30),
    )
    with pytest.raises(BaseSessionError) as expired:
        refresh_session(db, issued.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(hours=3))
    assert expired.value.code == "expired"
    other = start_session(db, user_id=10, keyset=keyset, audience=AUD, now=NOW)
    db.execute(update(base_sessions).where(base_sessions.c.id == other.session_id).values(
        expires_at=NOW - timedelta(minutes=1),
    ))
    db.commit()
    with pytest.raises(BaseSessionError) as session_expired:
        refresh_session(db, other.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=5))
    assert session_expired.value.code == "expired"


def test_revoked_session_disabled_user_and_role_are_rejected(env):
    db, _engine, keyset, _private = env
    _seed(db, 11, "other.employee", "employee", 2, "manager")
    first = start_session(db, user_id=10, keyset=keyset, audience=AUD, now=NOW)
    second = start_session(db, user_id=10, keyset=keyset, audience=AUD, now=NOW)
    other = start_session(db, user_id=11, keyset=keyset, audience=AUD, now=NOW)
    revoke_session(db, first.session_id, now=NOW)
    with pytest.raises(BaseSessionError) as revoked:
        refresh_session(db, first.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=1))
    assert revoked.value.code in {"revoked", "replay"}
    kept = refresh_session(db, second.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=1))
    assert kept.session_id == second.session_id
    still = refresh_session(db, other.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=1))
    assert still.session_id == other.session_id
    revoke_all_sessions(db, 10, now=NOW + timedelta(minutes=2))
    with pytest.raises(BaseSessionError):
        refresh_session(db, kept.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=3))
    alive = refresh_session(db, still.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=3))
    assert alive.session_id == other.session_id
    db.execute(update(accounts).where(accounts.c.id == 11).values(status="disabled"))
    db.commit()
    with pytest.raises(BaseSessionError) as disabled_user:
        refresh_session(db, alive.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=4))
    assert disabled_user.value.code == "denied"
    _seed(db, 12, "role.disabled", "employee", 3, "team_leader", role_status=0)
    blocked = start_session
    with pytest.raises(BaseSessionError) as disabled_role:
        blocked(db, user_id=12, keyset=keyset, audience=AUD, now=NOW)
    assert disabled_role.value.code == "denied"


def test_users_and_kids_stay_isolated(env):
    db, _engine, keyset, private_pem = env
    _seed(db, 13, "kid.other", "employee", 1, "employee")
    other_key = _pair()
    other_set = _keyset(*other_key, kid="base-next")
    current = start_session(db, user_id=10, keyset=keyset, audience=AUD, now=NOW)
    nxt = start_session(db, user_id=13, keyset=other_set, audience=AUD, now=NOW)
    revoke_sessions_for_kid(db, "base-current", now=NOW)
    with pytest.raises(BaseSessionError):
        refresh_session(db, current.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=1))
    kept = refresh_session(db, nxt.refresh_token, keyset=other_set, audience=AUD, now=NOW)
    header = jwt.get_unverified_header(kept.access_token)
    assert header["alg"] == "RS256" and header["kid"] == "base-next"
    claims = verify_token(other_set, kept.access_token, audience=AUD, token_use=ACCESS_TOKEN_USE)
    assert claims["sid"] == kept.session_id == nxt.session_id
    assert claims["token_use"] == ACCESS_TOKEN_USE
    assert claims["exp"] - claims["iat"] <= 3600
    assert "refresh" not in claims
    with pytest.raises(BaseTokenError):
        verify_token(other_set, kept.refresh_token, audience=AUD, token_use=ACCESS_TOKEN_USE)
    assert access_matches_session(
        db, kept.access_token, keyset=other_set, audience=AUD, now=NOW,
    )["sid"] == kept.session_id
    forged = jwt.encode(
        {**claims, "sid": "aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee"},
        private_pem, algorithm="RS256", headers={"kid": "base-current", "typ": "JWT"},
    )
    with pytest.raises(BaseSessionError):
        access_matches_session(db, forged, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=1))


def test_student_cannot_start_a_session(env):
    db, _engine, keyset, _private = env
    _seed(db, 14, "student.session", "student", 5, "student")
    with pytest.raises(BaseSessionError) as denied:
        start_session(db, user_id=14, keyset=keyset, audience=AUD, now=NOW)
    assert denied.value.code == "denied"
    assert db.execute(select(refresh_tokens.c.token_hash)).first() is None


def test_concurrent_refresh_keeps_one_winner_then_revokes_family(env):
    _db, engine, keyset, _private = env
    with Session(engine) as setup:
        issued = start_session(setup, user_id=10, keyset=keyset, audience=AUD, now=NOW)
    barrier = threading.Barrier(2)
    results = []

    def attempt():
        with Session(engine) as db:
            barrier.wait(timeout=5)
            try:
                item = refresh_session(
                    db, issued.refresh_token, keyset=keyset, audience=AUD,
                    now=NOW + timedelta(minutes=1),
                )
                results.append(("ok", item.refresh_token))
            except BaseSessionError as exc:
                results.append(("err", exc.code))

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert sorted(code for code, _value in results) == ["err", "ok"]
    assert dict(results)["err"] == "replay"
    winner = dict(results)["ok"]
    with Session(engine) as db:
        with pytest.raises(BaseSessionError):
            refresh_session(db, winner, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=2))
        row = db.execute(select(base_sessions).where(base_sessions.c.id == issued.session_id)).mappings().one()
        assert row["revoked_at"] is not None
        kids = set(db.execute(select(session_kids.c.kid)).scalars())
        assert "base-current" in kids
