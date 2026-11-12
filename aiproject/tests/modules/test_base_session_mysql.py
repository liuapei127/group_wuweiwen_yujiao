"""MySQL 8.0.27 concurrent refresh on a throwaway schema. Never writes education_service."""
from __future__ import annotations

import threading
import uuid
from datetime import timedelta
from pathlib import Path

import pymysql
import pytest
from sqlalchemy import create_engine, event, select, text
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

from app.core.database import engine as production_engine
from app.core.security.base_session import BaseSessionError, refresh_session, start_session
from app.core.security.base_session_schema import base_sessions, refresh_tokens
from tests.modules.test_base_session import AUD, NOW, _keyset, _pair

ROOT = Path(__file__).resolve().parents[2]
FORWARD = ROOT / "migrations" / "pending" / "003_base_refresh_token.sql"
BUSINESS_DATABASE = "education_service"


def test_mysql_concurrent_refresh_revokes_only_the_raced_family(monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("MySQL acceptance attempted the production SQLAlchemy engine")
    monkeypatch.setattr(production_engine, "connect", forbidden)
    settings = _settings()
    admin = _connect(settings, None)
    name = f"base_p3_{uuid.uuid4().hex[:12]}"
    assert name != BUSINESS_DATABASE
    try:
        with admin.cursor() as cursor:
            cursor.execute("SELECT VERSION()")
            version = cursor.fetchone()[0]
            if not str(version).startswith("8.0.27"):
                pytest.fail(f"MySQL concurrent path unverified: server version is {version}, expected 8.0.27")
            cursor.execute(
                f"CREATE DATABASE `{name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
        admin.commit()
        engine = _engine(settings, name)
        try:
            _install(engine)
            _assert_ddl(engine, name)
            keyset = _keyset(*_pair())
            with Session(engine) as setup:
                _seed(setup, 10, "mysql.racer")
                _seed(setup, 11, "mysql.bystander")
                raced = start_session(setup, user_id=10, keyset=keyset, audience=AUD, now=NOW)
                other = start_session(setup, user_id=11, keyset=keyset, audience=AUD, now=NOW)
            results = _race(engine, keyset, raced.refresh_token)
            assert sorted(code for code, _value in results) == ["err", "ok"]
            assert dict(results)["err"] == "replay"
            winner = dict(results)["ok"]
            with Session(engine) as check:
                original = check.execute(
                    select(refresh_tokens).where(refresh_tokens.c.token_hash == _hash(raced.refresh_token))
                ).mappings().one()
                assert original["used_at"] is not None
                family = check.execute(
                    select(refresh_tokens).where(refresh_tokens.c.family_id == raced.family_id)
                ).mappings().all()
                assert len(family) >= 2
                assert all(row["revoked_at"] is not None for row in family)
                session = check.execute(
                    select(base_sessions).where(base_sessions.c.id == raced.session_id)
                ).mappings().one()
                assert session["revoked_at"] is not None
                with pytest.raises(BaseSessionError) as dead:
                    refresh_session(check, winner, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=2))
                assert dead.value.code == "replay"
                kept = refresh_session(
                    check, other.refresh_token, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=2),
                )
                assert kept.session_id == other.session_id
                bystander = check.execute(
                    select(base_sessions).where(base_sessions.c.id == other.session_id)
                ).mappings().one()
                assert bystander["revoked_at"] is None
        finally:
            engine.dispose()
    finally:
        with admin.cursor() as cursor:
            cursor.execute(f"DROP DATABASE IF EXISTS `{name}`")
        admin.commit()
        admin.close()


def _settings() -> dict[str, str]:
    path = ROOT / ".env"
    found: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        found[key.strip()] = value.strip().strip('"').strip("'")
    needed = ("DB_HOST", "DB_PORT", "DB_USER", "DB_PASSWORD")
    if any(not found.get(key) for key in needed):
        pytest.fail("MySQL concurrent path unverified: local connection settings are incomplete")
    return found


def _connect(settings: dict[str, str], database: str | None):
    try:
        return pymysql.connect(
            host=settings["DB_HOST"],
            port=int(settings["DB_PORT"]),
            user=settings["DB_USER"],
            password=settings["DB_PASSWORD"],
            database=database,
            charset="utf8mb4",
            autocommit=False,
        )
    except pymysql.Error as exc:
        pytest.fail(f"MySQL concurrent path unverified: independent server unavailable ({exc.__class__.__name__})")


def _engine(settings: dict[str, str], database: str):
    def creator():
        return pymysql.connect(
            host=settings["DB_HOST"],
            port=int(settings["DB_PORT"]),
            user=settings["DB_USER"],
            password=settings["DB_PASSWORD"],
            database=database,
            charset="utf8mb4",
            autocommit=False,
        )

    engine = create_engine("mysql+pymysql://", creator=creator, poolclass=NullPool)

    @event.listens_for(engine, "connect")
    def _limit_lock_wait(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("SET SESSION innodb_lock_wait_timeout = 8")
        cursor.close()

    return engine


def _install(engine) -> None:
    script = "\n".join(
        line for line in FORWARD.read_text(encoding="utf-8").splitlines()
        if not line.strip().startswith("--")
    )
    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE ent_auth_session (
                id VARCHAR(36) NOT NULL,
                user_id BIGINT UNSIGNED NOT NULL,
                expires_at DATETIME NOT NULL,
                revoked_at DATETIME NULL,
                create_time DATETIME NOT NULL,
                PRIMARY KEY (id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE sys_role (
                id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
                role_code VARCHAR(32) NOT NULL,
                role_name VARCHAR(64) NOT NULL,
                status SMALLINT NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE sys_user (
                id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
                username VARCHAR(64) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                real_name VARCHAR(64) NOT NULL,
                user_type VARCHAR(16) NOT NULL,
                role_id BIGINT UNSIGNED NULL,
                status VARCHAR(16) NOT NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE ent_auth_role_permission (
                role_id BIGINT UNSIGNED NOT NULL,
                permission VARCHAR(96) NOT NULL,
                PRIMARY KEY (role_id, permission)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """
        ))
        for statement in (part.strip() for part in script.split(";")):
            if statement:
                conn.execute(text(statement))


def _assert_ddl(engine, database: str) -> None:
    with engine.connect() as conn:
        columns = conn.execute(text(
            """
            SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, CHARACTER_SET_NAME, COLLATION_NAME
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = :schema
              AND TABLE_NAME IN ('ent_auth_session', 'auth_user_session_kid', 'auth_refresh_token')
            """
        ), {"schema": database}).mappings().all()
    by_table: dict[str, dict] = {}
    for row in columns:
        by_table.setdefault(row["TABLE_NAME"], {})[row["COLUMN_NAME"]] = row
    assert "signing_kid" not in by_table["ent_auth_session"]
    session_id = by_table["ent_auth_session"]["id"]
    kid_session = by_table["auth_user_session_kid"]["session_id"]
    assert session_id["COLUMN_TYPE"] == "varchar(36)"
    assert session_id["COLLATION_NAME"] == "utf8mb4_unicode_ci"
    assert kid_session["COLUMN_TYPE"] == session_id["COLUMN_TYPE"]
    assert kid_session["CHARACTER_SET_NAME"] == session_id["CHARACTER_SET_NAME"]
    assert kid_session["COLLATION_NAME"] == session_id["COLLATION_NAME"]
    with engine.connect() as conn:
        indexes = conn.execute(text(
            """
            SELECT INDEX_NAME, NON_UNIQUE, COLUMN_NAME, SEQ_IN_INDEX
            FROM information_schema.STATISTICS
            WHERE TABLE_SCHEMA = :schema AND TABLE_NAME = 'auth_user_session_kid'
            ORDER BY INDEX_NAME, SEQ_IN_INDEX
            """
        ), {"schema": database}).mappings().all()
    primary = [row["COLUMN_NAME"] for row in indexes if row["INDEX_NAME"] == "PRIMARY"]
    kid_index = [row["COLUMN_NAME"] for row in indexes if row["INDEX_NAME"] == "idx_kid"]
    assert primary == ["session_id", "kid"]
    assert kid_index == ["kid"]


def _seed(db: Session, user_id: int, username: str) -> None:
    if db.execute(text("SELECT id FROM sys_role WHERE id = 1")).first() is None:
        db.execute(text(
            "INSERT INTO sys_role (id, role_code, role_name, status) VALUES (1, 'employee', 'employee', 1)"
        ))
    db.execute(text(
        """
        INSERT INTO sys_user (id, username, password_hash, real_name, user_type, role_id, status)
        VALUES (:id, :username, 'not-a-refresh-secret', :username, 'employee', 1, 'normal')
        """
    ), {"id": user_id, "username": username})
    db.commit()


def _race(engine, keyset, secret: str):
    barrier = threading.Barrier(2)
    results = []
    errors = []

    def attempt():
        with Session(engine) as db:
            barrier.wait(timeout=8)
            try:
                item = refresh_session(
                    db, secret, keyset=keyset, audience=AUD, now=NOW + timedelta(minutes=1),
                )
                results.append(("ok", item.refresh_token))
            except BaseSessionError as exc:
                results.append(("err", exc.code))
            except Exception as exc:
                errors.append(exc.__class__.__name__)

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert not errors, f"MySQL concurrent path hit {errors}"
    assert len(results) == 2
    return results


def _hash(secret: str) -> str:
    import hashlib
    return hashlib.sha256(secret.encode("ascii")).hexdigest()
