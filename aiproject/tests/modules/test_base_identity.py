"""BASE identity mapping on isolated SQLite. No production database and no token issuance."""
from __future__ import annotations

import jwt
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, insert, select, text
from sqlalchemy.orm import Session
from app.core.config import Settings
from app.core.database import engine as production_engine
from app.core.security.base_identity import (
    IDENTITY_ACCOUNT_COLUMNS,
    BaseIdentity,
    BaseIdentityError,
    resolve_identity,
)
from app.core.security.credentials import hash_password
from app.core.security.rbac import PERMISSIONS
from app.modules.auth.models import (
    AUTH_NEW_TABLES,
    accounts,
    login_attempts,
    role_permissions,
    roles,
    sessions,
)
from app.modules.auth.schemas import Login
from app.modules.auth.service import AuthService
from app.modules.auth import service as auth_service

PASSWORD = "isolated-test-password"
PLANTED_HASH = "planted-secret-hash-must-not-appear"


@pytest.fixture()
def db(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("identity test attempted production database access")
    monkeypatch.setattr(production_engine, "connect", forbidden)
    engine = create_engine("sqlite://")
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
        conn.execute(text(
            """
            CREATE TABLE student_info (
                id INTEGER PRIMARY KEY,
                user_id INTEGER,
                class_teacher_id INTEGER,
                student_no VARCHAR(32),
                school VARCHAR(64),
                major VARCHAR(64)
            )
            """
        ))
    roles.create(engine)
    for table in AUTH_NEW_TABLES:
        table.create(engine)
    from app.modules.consultant.models import VisitorIntake
    from app.modules.visitor.models import WebsiteStudentAccess
    VisitorIntake.__table__.create(engine)
    WebsiteStudentAccess.__table__.create(engine)
    session = Session(engine)
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


def _role(db, role_id, code, name, status=1):
    db.execute(insert(roles).values(id=role_id, role_code=code, role_name=name, status=status))


def _user(db, user_id, username, user_type, status="normal", role_id=None, password_hash=PLANTED_HASH):
    db.execute(insert(accounts).values(
        id=user_id, username=username, password_hash=password_hash, real_name=username,
        user_type=user_type, role_id=role_id, status=status,
    ))


def _grant(db, role_id, permission):
    db.execute(insert(role_permissions).values(role_id=role_id, permission=permission))


def test_selected_columns_exclude_password_hash():
    assert [column.key for column in IDENTITY_ACCOUNT_COLUMNS] == [
        "id", "username", "user_type", "status", "role_id", "role_code", "role_name", "role_status",
    ]
    assert "password_hash" not in BaseIdentity.__dataclass_fields__
    assert "sid" not in BaseIdentity.__dataclass_fields__


def test_employee_admin_and_student_are_distinct(db):
    _role(db, 1, "employee", "员工")
    _role(db, 2, "admin", "系统管理员")
    _role(db, 3, "student", "学生")
    _grant(db, 1, "crm:read")
    _grant(db, 2, "users:manage")
    _user(db, 10, "employee.one", "employee", role_id=1)
    _user(db, 11, "admin.one", "admin", role_id=2)
    _user(db, 12, "student.one", "student", role_id=3)
    employee = resolve_identity(db, 10)
    admin = resolve_identity(db, 11)
    student = resolve_identity(db, 12)
    assert employee.user_type == "employee" and employee.role_code == "employee"
    assert employee.sub == "10" and employee.permissions == frozenset({"crm:read"})
    assert employee.ent_login_allowed is True
    assert admin.user_type == "admin" and admin.role_code == "admin"
    assert admin.sub == "11" and admin.permissions == frozenset(PERMISSIONS)
    assert student.user_type == "student" and student.role_code == "student"
    assert student.sub == "12" and student.ent_login_allowed is False
    assert PLANTED_HASH not in repr((employee, admin, student))


def test_missing_and_disabled_accounts_are_rejected(db):
    _role(db, 1, "employee", "员工")
    _role(db, 3, "student", "学生")
    _user(db, 20, "employee.disabled", "employee", status="disabled", role_id=1)
    _user(db, 21, "student.disabled", "student", status="disabled", role_id=3)
    with pytest.raises(BaseIdentityError) as missing:
        resolve_identity(db, 999)
    assert missing.value.code == "missing"
    with pytest.raises(BaseIdentityError) as disabled_employee:
        resolve_identity(db, 20)
    assert disabled_employee.value.code == "disabled"
    with pytest.raises(BaseIdentityError) as disabled_student:
        resolve_identity(db, 21)
    assert disabled_student.value.code == "disabled"
    assert PLANTED_HASH not in str(disabled_employee.value)


def test_invalid_user_type_is_rejected(db):
    _role(db, 1, "employee", "员工")
    _user(db, 30, "guest.one", "guest", role_id=1)
    with pytest.raises(BaseIdentityError) as caught:
        resolve_identity(db, 30)
    assert caught.value.code == "invalid_user_type"


def test_missing_role_and_disabled_role_are_rejected(db):
    _role(db, 4, "manager", "部门经理", status=0)
    _user(db, 40, "employee.no-role", "employee", role_id=None)
    _user(db, 41, "employee.missing-role", "employee", role_id=404)
    _user(db, 42, "employee.disabled-role", "employee", role_id=4)
    assert _error(db, 40) == "missing_role"
    assert _error(db, 41) == "missing_role"
    assert _error(db, 42) == "disabled_role"


def test_employee_role_does_not_change_account_class(db):
    _role(db, 2, "admin", "系统管理员")
    _role(db, 5, "manager", "部门经理")
    _role(db, 6, "team_leader", "班主任")
    _grant(db, 2, "crm:read")
    _grant(db, 2, "users:manage")
    _grant(db, 2, "not-a-catalogue-permission")
    _grant(db, 5, "directory:read")
    _grant(db, 6, "leaves:read")
    _user(db, 50, "employee.manager", "employee", role_id=5)
    _user(db, 51, "employee.leader", "employee", role_id=6)
    _user(db, 52, "employee.with-admin-role", "employee", role_id=2)
    _user(db, 53, "admin.with-admin-role", "admin", role_id=2)
    manager = resolve_identity(db, 50)
    leader = resolve_identity(db, 51)
    employee_admin_role = resolve_identity(db, 52)
    admin_account = resolve_identity(db, 53)
    assert manager.user_type == "employee" and manager.role_code == "manager"
    assert manager.permissions == frozenset({"directory:read"})
    assert leader.user_type == "employee" and leader.role_code == "team_leader"
    assert leader.permissions == frozenset({"leaves:read"})
    assert employee_admin_role.user_type == "employee"
    assert admin_account.user_type == "admin"
    assert employee_admin_role.role_code == admin_account.role_code == "admin"
    assert employee_admin_role.permissions == admin_account.permissions == frozenset(PERMISSIONS)
    assert "not-a-catalogue-permission" not in employee_admin_role.permissions


def test_admin_without_stored_grants_has_all_permissions_and_remains_an_admin(db):
    from app.modules.auth.repository import AuthRepository
    _role(db, 2, "admin", "管理员")
    _user(db, 11, "admin.one", "admin", role_id=2)
    repo = AuthRepository(db)
    assert repo.permissions(2) == set(PERMISSIONS)
    assert resolve_identity(db, 11).permissions == frozenset(PERMISSIONS)
    assert repo.list_roles()[0]["permissions"] == sorted(PERMISSIONS)
    assert repo.admin_count() == 1
    db.execute(accounts.update().where(accounts.c.id == 11).values(status="disabled"))
    assert repo.admin_count() == 0
    assert _error(db, 11) == "disabled"


def test_saving_admin_normalizes_all_permissions_and_audit(db):
    import json
    from types import SimpleNamespace
    from app.modules.auth.schemas import RoleWrite
    from app.modules.auth.models import audit_log
    _role(db, 2, "admin", "管理员")
    _user(db, 11, "admin.one", "admin", role_id=2)
    AuthService(db).save_role(RoleWrite(role_code="admin", role_name="管理员", permissions=[]),
                              SimpleNamespace(employee_id=11), role_id=2)
    assert set(db.scalars(select(role_permissions.c.permission).where(role_permissions.c.role_id == 2))) == set(PERMISSIONS)
    details = json.loads(db.scalar(select(audit_log.c.details)))
    assert set(details["permissions"]) == set(PERMISSIONS)


def test_student_can_be_identified_but_existing_login_rejects(db, monkeypatch):
    password_hash = hash_password(PASSWORD)
    _role(db, 3, "student", "学生")
    _role(db, 1, "employee", "员工")
    _user(db, 60, "13900002160", "student", role_id=3, password_hash=password_hash)
    _user(db, 61, "13900002161", "employee", role_id=1, password_hash=password_hash)
    db.commit()
    student = resolve_identity(db, 60)
    assert student.user_type == "student" and student.ent_login_allowed is False
    assert student.sub == "60"
    settings = Settings(
        _env_file=None,
        employee_identity_mode="trusted_jwt",
        auth_jwt_secret="portal-test-secret-value-32chars",
    )
    monkeypatch.setattr(auth_service, "get_settings", lambda: settings)
    with pytest.raises(HTTPException) as denied:
        AuthService(db).login(Login(username="13900002160", password=PASSWORD), "127.0.0.1")
    assert denied.value.status_code == 401
    assert db.scalar(select(func.count()).select_from(sessions)) == 0
    result = AuthService(db).login(Login(username="13900002161", password=PASSWORD), "127.0.0.1")
    assert jwt.get_unverified_header(result["access_token"])["alg"] == "HS256"
    assert resolve_identity(db, 61).user_type == "employee"
    assert db.scalar(select(func.count()).select_from(login_attempts)) == 1


def test_username_is_not_used_to_guess_identity(db):
    _role(db, 2, "admin", "系统管理员")
    _user(db, 70, "admin", "employee", role_id=2)
    identity = resolve_identity(db, 70)
    assert identity.username == "admin"
    assert identity.user_type == "employee"
    with pytest.raises(BaseIdentityError) as caught:
        resolve_identity(db, "admin")
    assert caught.value.code == "missing"


def _error(db, user_id) -> str:
    with pytest.raises(BaseIdentityError) as caught:
        resolve_identity(db, user_id)
    return caught.value.code
