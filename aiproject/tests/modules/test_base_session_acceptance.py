"""Phase-3 acceptance gaps. Isolated SQLite; no production database writes."""
from __future__ import annotations

from datetime import timedelta
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select, update
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.database import engine as production_engine

from app.core.security.base_jwt import ACCESS_TOKEN_USE, verify_token
from app.core.security.base_session import (
    IDLE_TTL_MAX,
    REFRESH_TTL_MAX,
    RETENTION,
    SESSION_TTL_MAX,
    BaseSessionError,
    note_verified_access,
    purge_expired_families,
    refresh_session,
    revoke_sessions_for_kid,
    start_session,
)
from app.core.security.base_session_schema import base_sessions, refresh_tokens, session_kids
from tests.modules.test_base_session import AUD, NOW, _keyset, _pair, _prepare, _seed

@pytest.fixture()
def env(monkeypatch, tmp_path):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("acceptance test attempted production database access")
    monkeypatch.setattr(production_engine, "connect", forbidden)
    engine = create_engine(f"sqlite:///{tmp_path / 'accept.db'}", poolclass=NullPool)
    _prepare(engine)
    keyset = _keyset(*_pair())
    db = Session(engine)
    _seed(db, 10, "employee.session", "employee", 1, "employee")
    try:
        yield db, engine, keyset, None
    finally:
        db.close()
        engine.dispose()


ROOT = Path(__file__).resolve().parents[2]
FORWARD = ROOT / "migrations" / "pending" / "003_base_refresh_token.sql"
ROLLBACK = ROOT / "migrations" / "pending" / "003_base_refresh_token_rollback.sql"


def test_lifecycle_limits_and_absolute_end(env):
    db, _engine, keyset, _private = env
    with pytest.raises(BaseSessionError):
        start_session(
            db, user_id=10, keyset=keyset, audience=AUD, now=NOW,
            refresh_ttl=REFRESH_TTL_MAX + timedelta(seconds=1),
        )
    with pytest.raises(BaseSessionError):
        start_session(
            db, user_id=10, keyset=keyset, audience=AUD, now=NOW,
            session_ttl=SESSION_TTL_MAX + timedelta(seconds=1),
        )
    issued = start_session(
        db, user_id=10, keyset=keyset, audience=AUD, now=NOW,
        session_ttl=timedelta(hours=1), refresh_ttl=timedelta(hours=12),
    )
    with pytest.raises(BaseSessionError):
        refresh_session(
            db, issued.refresh_token, keyset=keyset, audience=AUD, now=NOW,
            idle_ttl=IDLE_TTL_MAX + timedelta(seconds=1),
        )
    session = db.execute(select(base_sessions).where(base_sessions.c.id == issued.session_id)).mappings().one()
    stored = db.execute(select(refresh_tokens).where(refresh_tokens.c.session_id == issued.session_id)).mappings().one()
    assert session["expires_at"] - session["create_time"] == timedelta(hours=1)
    assert stored["expires_at"] == session["expires_at"]
    claims = verify_token(keyset, issued.access_token, audience=AUD, token_use=ACCESS_TOKEN_USE)
    assert claims["exp"] - claims["iat"] == 3600
    assert claims["sid"] == issued.session_id


def test_last_used_is_conditional_and_idle_revokes_family(env):
    db, _engine, keyset, _private = env
    issued = start_session(db, user_id=10, keyset=keyset, audience=AUD, now=NOW)
    note_verified_access(db, issued.access_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=1))
    assert _last_used(db, issued.session_id) == NOW
    note_verified_access(db, issued.access_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=6))
    assert _last_used(db, issued.session_id) == NOW + timedelta(minutes=6)
    rotated = refresh_session(
        db, issued.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=12),
    )
    assert _last_used(db, issued.session_id) == NOW + timedelta(minutes=12)
    refresh_session(db, rotated.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=13))
    assert _last_used(db, issued.session_id) == NOW + timedelta(minutes=12)
    with pytest.raises(BaseSessionError) as idle:
        note_verified_access(
            db, issued.access_token, keyset=keyset, audience=AUD,
            now=NOW + timedelta(minutes=12) + timedelta(hours=2, seconds=1),
        )
    assert idle.value.code == "expired"
    rows = db.execute(select(refresh_tokens).where(refresh_tokens.c.family_id == issued.family_id)).mappings().all()
    assert rows and all(row["revoked_at"] is not None for row in rows)
    session = db.execute(select(base_sessions).where(base_sessions.c.id == issued.session_id)).mappings().one()
    assert session["revoked_at"] is not None


def test_kid_history_survives_rotation_and_leak_is_scoped(env):
    db, _engine, keyset, _private = env
    _seed(db, 15, "only.k2", "employee", 1, "employee")
    other = _keyset(*_pair(), kid="base-next")
    both = start_session(db, user_id=10, keyset=keyset, audience=AUD, now=NOW)
    rotated = refresh_session(
        db, both.refresh_token, keyset=other, audience=AUD, now=NOW + timedelta(minutes=6),
    )
    again = refresh_session(
        db, rotated.refresh_token, keyset=other, audience=AUD, now=NOW + timedelta(minutes=20),
    )
    recorded = {
        row["kid"]: row["first_issued_at"]
        for row in db.execute(select(session_kids).where(session_kids.c.session_id == both.session_id)).mappings()
    }
    assert recorded["base-current"] == NOW
    assert recorded["base-next"] == NOW + timedelta(minutes=6)
    only_k2 = start_session(db, user_id=15, keyset=other, audience=AUD, now=NOW)
    revoke_sessions_for_kid(db, "base-current", now=NOW + timedelta(minutes=21))
    with pytest.raises(BaseSessionError):
        refresh_session(db, again.refresh_token, keyset=other, audience=AUD, now=NOW + timedelta(minutes=22))
    kept = refresh_session(db, only_k2.refresh_token, keyset=other, audience=AUD, now=NOW + timedelta(minutes=22))
    assert kept.session_id == only_k2.session_id


def test_kid_insert_rolls_back_with_the_refresh(env, monkeypatch):
    db, _engine, keyset, _private = env
    issued = start_session(db, user_id=10, keyset=keyset, audience=AUD, now=NOW)

    def fail_kid(*_args, **_kwargs):
        raise RuntimeError("kid write failed")

    monkeypatch.setattr("app.core.security.base_session._remember_kid", fail_kid)
    with pytest.raises(RuntimeError):
        refresh_session(db, issued.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=6))
    monkeypatch.undo()
    rotated = refresh_session(db, issued.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=6))
    assert rotated.refresh_token != issued.refresh_token


def test_retention_keeps_replay_markers_and_purges_whole_families(env):
    db, engine, keyset, _private = env
    _seed(db, 16, "still.live", "employee", 1, "employee")
    live = start_session(db, user_id=16, keyset=keyset, audience=AUD, now=NOW)
    recent = start_session(
        db, user_id=10, keyset=keyset, audience=AUD, now=NOW - timedelta(hours=2),
        refresh_ttl=timedelta(minutes=30), session_ttl=timedelta(hours=12),
    )
    assert purge_expired_families(db, now=NOW) == 0
    with pytest.raises(BaseSessionError) as expired:
        refresh_session(db, recent.refresh_token, keyset=keyset, audience=AUD, now=NOW)
    assert expired.value.code == "expired"
    old = start_session(
        db, user_id=10, keyset=keyset, audience=AUD, now=NOW - timedelta(days=8),
        refresh_ttl=timedelta(hours=1), session_ttl=timedelta(hours=1),
    )
    used = refresh_session(
        db, old.refresh_token, keyset=keyset, audience=AUD,
        now=NOW - timedelta(days=8) + timedelta(minutes=6),
    )
    with pytest.raises(BaseSessionError) as replay:
        refresh_session(db, old.refresh_token, keyset=keyset, audience=AUD, now=NOW - timedelta(days=8) + timedelta(minutes=7))
    assert replay.value.code == "replay"
    assert purge_expired_families(db, now=NOW - timedelta(days=8) + timedelta(days=3)) == 0
    _age_family(db, old.family_id, NOW - RETENTION - timedelta(days=1))
    assert purge_expired_families(db, now=NOW) == 1
    with pytest.raises(BaseSessionError) as gone:
        refresh_session(db, old.refresh_token, keyset=keyset, audience=AUD, now=NOW)
    assert gone.value.code == "invalid"
    assert used.refresh_token not in _token_secrets(db)
    kept = refresh_session(db, live.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=6))
    assert kept.session_id == live.session_id
    _assert_cleanup_is_atomic(engine, db, keyset)


def test_pending_ddl_matches_session_rules():
    forward = FORWARD.read_text(encoding="utf-8")
    rollback = ROLLBACK.read_text(encoding="utf-8")
    statements = "\n".join(line for line in forward.splitlines() if not line.strip().startswith("--"))
    assert "signing_kid" not in statements.lower()
    assert "utf8mb4_unicode_ci" in forward
    assert "PRIMARY KEY (session_id, kid)" in forward
    assert "KEY idx_kid (kid)" in forward
    assert "token_hash" in forward and "family_id" in forward and "replaced_by" in forward
    assert "last_used_at" in forward and "parent_session_id" in forward
    assert rollback.index("auth_user_session_kid") < rollback.index("auth_refresh_token")
    assert "DROP TABLE ent_auth_session" not in rollback
    assert "DROP COLUMN parent_session_id" in rollback


def test_sqlite_kid_index_and_primary_key(env):
    _db, engine, _keyset, _private = env
    inspector = sa_inspect(engine)
    primary = inspector.get_pk_constraint("auth_user_session_kid")["constrained_columns"]
    assert primary == ["session_id", "kid"]
    indexes = inspector.get_indexes("auth_user_session_kid")
    assert any(item["name"] == "idx_kid" and item["column_names"] == ["kid"] for item in indexes)


def _last_used(db, session_id):
    return db.execute(select(base_sessions.c.last_used_at).where(base_sessions.c.id == session_id)).scalar_one()


def _token_secrets(db):
    return set(db.execute(select(refresh_tokens.c.token_hash)).scalars())


def _age_family(db, family_id, moment):
    db.execute(
        update(refresh_tokens).where(refresh_tokens.c.family_id == family_id).values(
            expires_at=moment, used_at=moment, revoked_at=moment,
        )
    )
    session_ids = list(db.execute(
        select(refresh_tokens.c.session_id).where(refresh_tokens.c.family_id == family_id)
    ).scalars())
    db.execute(
        update(base_sessions).where(base_sessions.c.id.in_(session_ids)).values(
            expires_at=moment, revoked_at=moment, last_used_at=moment,
        )
    )
    db.commit()


def _assert_cleanup_is_atomic(engine, db, keyset):
    issued = start_session(
        db, user_id=10, keyset=keyset, audience=AUD, now=NOW - timedelta(days=9),
        refresh_ttl=timedelta(hours=1), session_ttl=timedelta(hours=1),
    )
    _age_family(db, issued.family_id, NOW - timedelta(days=8))

    def fail_session_delete(conn, cursor, statement, parameters, context, executemany):
        if "DELETE FROM ent_auth_session" in statement:
            raise RuntimeError("cleanup failed")

    event.listen(engine, "before_cursor_execute", fail_session_delete)
    try:
        with pytest.raises(RuntimeError):
            purge_expired_families(db, now=NOW)
    finally:
        event.remove(engine, "before_cursor_execute", fail_session_delete)
    assert db.execute(
        select(refresh_tokens.c.family_id).where(refresh_tokens.c.family_id == issued.family_id)
    ).first() is not None
