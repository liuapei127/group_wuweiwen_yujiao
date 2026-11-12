"""Phase-3 acceptance gaps. Isolated SQLite; no production database writes."""
from __future__ import annotations

from datetime import timedelta, timezone
from pathlib import Path

import jwt
import pytest
from sqlalchemy import create_engine, delete, event, select, update
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import DisconnectionError, InterfaceError, OperationalError
from sqlalchemy.exc import TimeoutError as StoreTimeout
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.database import engine as production_engine
from app.core.security.base_jwt import ACCESS_TOKEN_USE, BaseTokenError, issue_access_token, verify_token
from app.core.security.base_session import (
    IDLE_TTL_MAX,
    REFRESH_TTL_MAX,
    RETENTION,
    SESSION_TTL_MAX,
    BaseSessionError,
    BaseSessionUnavailable,
    access_matches_session,
    authorize_access,
    end_login,
    note_verified_access,
    purge_expired_families,
    refresh_session,
    revoke_all_sessions,
    revoke_sessions_for_kid,
    revoke_user_sessions,
    session_failure_status,
    start_session,
)
from app.core.security.base_session_schema import base_sessions, refresh_tokens, session_kids
from app.modules.auth.models import accounts, role_permissions, roles
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


def test_revoke_joins_the_caller_or_commits_on_its_own(env):
    db, engine, keyset, _private = env
    _seed(db, 15, "other.session", "employee", 1, "employee")
    own = start_session(db, user_id=10, keyset=keyset, audience=AUD, now=NOW)
    other = start_session(db, user_id=15, keyset=keyset, audience=AUD, now=NOW)
    with pytest.raises(ValueError):
        revoke_user_sessions(db, 10, now=NOW)
    kept = refresh_session(db, own.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=6))
    try:
        with db.begin():
            revoke_user_sessions(db, 10, now=NOW + timedelta(minutes=7))
            raise RuntimeError("caller failed")
    except RuntimeError:
        pass
    again = refresh_session(db, kept.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=8))
    with db.begin():
        revoke_user_sessions(db, 10, now=NOW + timedelta(minutes=9))
    with Session(engine) as seen:
        assert seen.execute(
            select(base_sessions.c.revoked_at).where(base_sessions.c.id == own.session_id)
        ).scalar_one() is not None
        assert seen.execute(
            select(base_sessions.c.revoked_at).where(base_sessions.c.id == other.session_id)
        ).scalar_one() is None
    with pytest.raises(BaseSessionError):
        refresh_session(db, again.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=10))
    other_live = refresh_session(db, other.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=10))
    revoke_all_sessions(db, 15, now=NOW + timedelta(minutes=11))
    with Session(engine) as seen:
        assert seen.execute(
            select(base_sessions.c.revoked_at).where(base_sessions.c.id == other_live.session_id)
        ).scalar_one() is not None
        assert seen.execute(
            select(base_sessions.c.revoked_at).where(base_sessions.c.id == own.session_id)
        ).scalar_one() is not None


def test_protected_request_rereads_account_role_and_permission(env):
    db, _engine, keyset, _private = env
    issued = start_session(db, user_id=10, keyset=keyset, audience=AUD, now=NOW)
    assert note_verified_access(
        db, issued.access_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=1),
    )["sid"] == issued.session_id
    with pytest.raises(BaseSessionError) as denied:
        authorize_access(
            db, issued.access_token, keyset=keyset, audience=AUD, permission="dashboard:read",
            now=NOW + timedelta(minutes=6),
        )
    assert denied.value.code == "denied"
    assert session_failure_status(denied.value) == 401
    assert _last_used(db, issued.session_id) == NOW
    _grant(db, "dashboard:read")
    allowed = authorize_access(
        db, issued.access_token, keyset=keyset, audience=AUD, permission="dashboard:read",
        now=NOW + timedelta(minutes=6),
    )
    assert allowed.identity.user_id == 10
    assert allowed.identity.user_type == "employee"
    assert "dashboard:read" in allowed.identity.permissions
    assert _last_used(db, issued.session_id) == NOW + timedelta(minutes=6)
    db.execute(delete(role_permissions).where(role_permissions.c.role_id == 1))
    db.commit()
    with pytest.raises(BaseSessionError):
        authorize_access(
            db, issued.access_token, keyset=keyset, audience=AUD, permission="dashboard:read",
            now=NOW + timedelta(minutes=12),
        )
    assert _last_used(db, issued.session_id) == NOW + timedelta(minutes=6)
    _grant(db, "dashboard:read")
    db.execute(update(accounts).where(accounts.c.id == 10).values(status="disabled"))
    db.commit()
    with pytest.raises(BaseSessionError) as disabled:
        authorize_access(
            db, issued.access_token, keyset=keyset, audience=AUD, permission="dashboard:read",
            now=NOW + timedelta(minutes=13),
        )
    assert disabled.value.code == "denied"
    assert note_verified_access(
        db, issued.access_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=13),
    )["sub"] == "10"
    db.execute(update(accounts).where(accounts.c.id == 10).values(status="normal", user_type="student"))
    db.commit()
    with pytest.raises(BaseSessionError) as student:
        authorize_access(
            db, issued.access_token, keyset=keyset, audience=AUD, permission="dashboard:read",
            now=NOW + timedelta(minutes=20),
        )
    assert student.value.code == "denied"
    db.execute(update(accounts).where(accounts.c.id == 10).values(user_type="employee"))
    db.execute(update(roles).where(roles.c.id == 1).values(status=0))
    db.commit()
    with pytest.raises(BaseSessionError) as role:
        authorize_access(
            db, issued.access_token, keyset=keyset, audience=AUD, permission="dashboard:read",
            now=NOW + timedelta(minutes=21),
        )
    assert role.value.code == "denied"


def test_logout_revokes_without_creating_a_session(env, monkeypatch):
    db, _engine, keyset, _private = env
    current = start_session(db, user_id=10, keyset=keyset, audience=AUD, now=NOW)
    live = start_session(db, user_id=10, keyset=keyset, audience=AUD, now=NOW)
    expired_access = issue_access_token(
        keyset, sub="10", sid=live.session_id, audience=AUD, user_type="employee",
        now=(NOW - timedelta(hours=2)).replace(tzinfo=timezone.utc),
    )
    old = start_session(
        db, user_id=10, keyset=keyset, audience=AUD, now=NOW - timedelta(hours=3),
        refresh_ttl=timedelta(minutes=30), session_ttl=timedelta(hours=1),
    )
    untouched = start_session(db, user_id=10, keyset=keyset, audience=AUD, now=NOW)

    def forbid(*_args, **_kwargs):
        raise AssertionError("logout created a login")

    monkeypatch.setattr("app.core.security.base_session.start_session", forbid)
    monkeypatch.setattr("app.core.security.base_session.refresh_session", forbid)
    before_ids = _session_ids(db)
    before_hashes = _token_hashes(db)
    assert end_login(
        db, access_token=current.access_token, refresh_token=current.refresh_token,
        keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=1),
    ) == "revoked"
    assert _session_ids(db) == before_ids
    assert _token_hashes(db) == before_hashes
    assert _revoked(db, current.session_id)
    assert end_login(
        db, access_token=expired_access, refresh_token=live.refresh_token,
        keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=2),
    ) == "revoked"
    assert _revoked(db, live.session_id)
    assert end_login(
        db, access_token=old.access_token, refresh_token=old.refresh_token,
        keyset=keyset, audience=AUD, now=NOW,
    ) == "already_logged_out"
    assert _revoked(db, old.session_id) is None
    assert end_login(
        db, access_token=None, refresh_token=None, keyset=keyset, audience=AUD, now=NOW,
    ) == "already_logged_out"
    assert end_login(
        db, access_token="", refresh_token="", keyset=keyset, audience=AUD, now=NOW,
    ) == "already_logged_out"
    assert _session_ids(db) == before_ids
    assert _token_hashes(db) == before_hashes
    assert _revoked(db, untouched.session_id) is None


def test_database_failure_rejects_instead_of_accepting_the_signature(env, monkeypatch):
    db, _engine, keyset, _private = env
    issued = start_session(db, user_id=10, keyset=keyset, audience=AUD, now=NOW)
    _grant(db, "dashboard:read")

    import app.core.security.base_session as session_mod
    original_session = session_mod._session
    original_touch = session_mod._touch_last_used
    original_identity = session_mod.resolve_identity

    def fail_read(*_args, **_kwargs):
        raise OperationalError("SELECT", {}, Exception("unavailable"))

    monkeypatch.setattr(session_mod, "_session", fail_read)
    with pytest.raises(BaseSessionUnavailable) as failed:
        note_verified_access(db, issued.access_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=6))
    assert session_failure_status(failed.value) == 503
    with pytest.raises(BaseSessionUnavailable) as denied:
        authorize_access(
            db, issued.access_token, keyset=keyset, audience=AUD, permission="dashboard:read",
            now=NOW + timedelta(minutes=6),
        )
    assert session_failure_status(denied.value) == 503
    assert _last_used(db, issued.session_id) == NOW
    monkeypatch.setattr(session_mod, "_session", original_session)

    def fail_touch(*_args, **_kwargs):
        raise OperationalError("UPDATE", {}, Exception("unavailable"))

    monkeypatch.setattr(session_mod, "_touch_last_used", fail_touch)
    with pytest.raises(BaseSessionUnavailable) as touch:
        authorize_access(
            db, issued.access_token, keyset=keyset, audience=AUD, permission="dashboard:read",
            now=NOW + timedelta(minutes=6),
        )
    assert session_failure_status(touch.value) == 503
    assert _last_used(db, issued.session_id) == NOW
    monkeypatch.setattr(session_mod, "_touch_last_used", original_touch)

    def fail_identity(*_args, **_kwargs):
        raise OperationalError("SELECT", {}, Exception("unavailable"))

    monkeypatch.setattr(session_mod, "resolve_identity", fail_identity)
    with pytest.raises(BaseSessionUnavailable):
        authorize_access(
            db, issued.access_token, keyset=keyset, audience=AUD, permission="dashboard:read",
            now=NOW + timedelta(minutes=6),
        )
    assert _last_used(db, issued.session_id) == NOW
    monkeypatch.setattr(session_mod, "resolve_identity", original_identity)
    monkeypatch.setattr(session_mod, "_session", fail_read)
    with pytest.raises(BaseSessionUnavailable) as logout:
        end_login(
            db, access_token=issued.access_token, refresh_token=issued.refresh_token,
            keyset=keyset, audience=AUD, now=NOW,
        )
    assert session_failure_status(logout.value) == 503
    assert _revoked(db, issued.session_id) is None


def test_access_subject_must_match_session_user(env):
    db, _engine, keyset, _private = env
    _seed(db, 15, "other.session", "employee", 1, "employee")
    own = start_session(db, user_id=10, keyset=keyset, audience=AUD, now=NOW)
    victim = start_session(db, user_id=15, keyset=keyset, audience=AUD, now=NOW)
    claims = verify_token(keyset, own.access_token, audience=AUD, token_use=ACCESS_TOKEN_USE)
    stored_user = db.execute(
        select(base_sessions.c.user_id).where(base_sessions.c.id == own.session_id)
    ).scalar_one()
    assert claims["sub"] == str(int(stored_user)) == "10"
    forged = jwt.encode(
        {**claims, "sid": victim.session_id},
        keyset.signing_key().private_pem,
        algorithm="RS256",
        headers={"kid": keyset.signing_key().kid, "typ": "JWT"},
    )
    for use in (
        lambda: note_verified_access(
            db, forged, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=1),
        ),
        lambda: authorize_access(
            db, forged, keyset=keyset, audience=AUD, permission="dashboard:read",
            now=NOW + timedelta(minutes=1),
        ),
        lambda: access_matches_session(
            db, forged, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=1),
        ),
    ):
        with pytest.raises(BaseSessionError) as mismatch:
            use()
        assert mismatch.value.code == "invalid"
    with pytest.raises(BaseSessionError) as logout:
        end_login(
            db, access_token=forged, refresh_token=victim.refresh_token,
            keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=1),
        )
    assert logout.value.code == "invalid"
    assert session_failure_status(logout.value) == 401
    assert _revoked(db, victim.session_id) is None
    assert _revoked(db, own.session_id) is None
    kept = refresh_session(db, victim.refresh_token, keyset=keyset, audience=AUD, now=NOW)
    assert kept.session_id == victim.session_id
    kept_claims = verify_token(keyset, kept.access_token, audience=AUD, token_use=ACCESS_TOKEN_USE)
    assert kept_claims["sub"] == "15"
    assert int(db.execute(
        select(base_sessions.c.user_id).where(base_sessions.c.id == kept.session_id)
    ).scalar_one()) == 15
    db.execute(
        update(refresh_tokens).where(refresh_tokens.c.session_id == own.session_id).values(user_id=15)
    )
    db.commit()
    with pytest.raises(BaseSessionError) as rebound:
        refresh_session(db, own.refresh_token, keyset=keyset, audience=AUD, now=NOW)
    assert rebound.value.code == "invalid"
    assert _revoked(db, own.session_id) is None
    assert access_matches_session(
        db, own.access_token, keyset=keyset, audience=AUD, now=NOW,
    )["sub"] == "10"


@pytest.mark.parametrize("make_error", [
    lambda: InterfaceError("SELECT", {}, Exception("closed")),
    lambda: DisconnectionError("closed"),
    lambda: StoreTimeout("timeout"),
])
def test_disconnect_and_timeout_fail_closed(env, monkeypatch, make_error):
    db, _engine, keyset, _private = env
    issued = start_session(db, user_id=10, keyset=keyset, audience=AUD, now=NOW)
    _grant(db, "dashboard:read")
    import app.core.security.base_session as session_mod

    original_session = session_mod._session

    def fail_read(*_args, **_kwargs):
        raise make_error()

    monkeypatch.setattr(session_mod, "_session", fail_read)
    with pytest.raises(BaseSessionUnavailable) as denied:
        authorize_access(
            db, issued.access_token, keyset=keyset, audience=AUD, permission="dashboard:read",
            now=NOW + timedelta(minutes=6),
        )
    assert session_failure_status(denied.value) == 503
    with pytest.raises(BaseSessionUnavailable) as logout:
        end_login(
            db, access_token=issued.access_token, refresh_token=issued.refresh_token,
            keyset=keyset, audience=AUD, now=NOW,
        )
    assert session_failure_status(logout.value) == 503
    assert _revoked(db, issued.session_id) is None
    assert _last_used(db, issued.session_id) == NOW
    monkeypatch.setattr(session_mod, "_session", original_session)

    def fail_touch(*_args, **_kwargs):
        raise make_error()

    monkeypatch.setattr(session_mod, "_touch_last_used", fail_touch)
    with pytest.raises(BaseSessionUnavailable) as touch:
        authorize_access(
            db, issued.access_token, keyset=keyset, audience=AUD, permission="dashboard:read",
            now=NOW + timedelta(minutes=6),
        )
    assert session_failure_status(touch.value) == 503
    assert _last_used(db, issued.session_id) == NOW
    assert _revoked(db, issued.session_id) is None


def test_refresh_logout_accepts_only_a_genuinely_expired_access(env):
    db, _engine, keyset, _private = env
    live = start_session(db, user_id=10, keyset=keyset, audience=AUD, now=NOW)
    claims = verify_token(keyset, live.access_token, audience=AUD, token_use=ACCESS_TOKEN_USE)
    private = keyset.signing_key().private_pem
    header = {"kid": keyset.signing_key().kid, "typ": "JWT"}
    other_private, _other_public = _pair()
    rejected_tokens = (
        jwt.encode(dict(claims), other_private, algorithm="RS256", headers=header),
        jwt.encode({**claims, "iss": "ent-portal"}, private, algorithm="RS256", headers=header),
        jwt.encode({**claims, "aud": "edu-api:stu"}, private, algorithm="RS256", headers=header),
        issue_access_token(
            keyset, sub="10", sid=live.session_id, audience="edu-api:stu", user_type="employee",
            now=(NOW - timedelta(hours=2)).replace(tzinfo=timezone.utc),
        ),
    )
    for token in rejected_tokens:
        with pytest.raises(BaseTokenError) as rejected:
            end_login(
                db, access_token=token, refresh_token=live.refresh_token,
                keyset=keyset, audience=AUD, now=NOW,
            )
        assert session_failure_status(rejected.value) == 401
        assert _revoked(db, live.session_id) is None
    genuine = issue_access_token(
        keyset, sub="10", sid=live.session_id, audience=AUD, user_type="employee",
        now=(NOW - timedelta(hours=2)).replace(tzinfo=timezone.utc),
    )
    assert end_login(
        db, access_token=genuine, refresh_token=live.refresh_token,
        keyset=keyset, audience=AUD, now=NOW,
    ) == "revoked"
    assert _revoked(db, live.session_id) is not None


def _grant(db, permission: str) -> None:
    if db.execute(
        select(role_permissions.c.permission).where(
            role_permissions.c.role_id == 1, role_permissions.c.permission == permission,
        )
    ).first() is None:
        db.execute(role_permissions.insert().values(role_id=1, permission=permission))
        db.commit()


def _session_ids(db):
    return set(db.execute(select(base_sessions.c.id)).scalars())


def _token_hashes(db):
    return set(db.execute(select(refresh_tokens.c.token_hash)).scalars())


def _revoked(db, session_id):
    return db.execute(
        select(base_sessions.c.revoked_at).where(base_sessions.c.id == session_id)
    ).scalar_one()


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
