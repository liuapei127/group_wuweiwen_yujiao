from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import dependencies
from app.core.security.base_session_schema import refresh_tokens, session_kids
from app.core.security.credentials import hash_password
from app.modules.auth import base_portal, router as auth_router, service as auth_service
from app.modules.auth.models import role_permissions, roles
from tests.integration.test_ent_portal_routes import isolated_portal
from tests.modules.test_base_session import _keyset, _pair


def test_base_employee_cookies_refresh_replay_and_logout(isolated_portal, monkeypatch):
    app, engine = isolated_portal("base_rs256")
    settings = Settings(
        _env_file=None, employee_identity_mode="base_rs256",
        base_portal_origin="https://portal.example.test",
    )
    for module in (base_portal, auth_router, auth_service, dependencies):
        monkeypatch.setattr(module, "get_settings", lambda: settings)
    monkeypatch.setattr(base_portal, "load_keyset", lambda: keyset)
    keyset = _keyset(*_pair())

    try:
        with Session(engine) as db:
            for query in (
                "ALTER TABLE ent_auth_session ADD last_used_at DATETIME",
                "ALTER TABLE ent_auth_session ADD parent_session_id VARCHAR(36)",
                "ALTER TABLE sys_user ADD username VARCHAR(64)",
                "ALTER TABLE sys_user ADD password_hash VARCHAR(255)",
                "ALTER TABLE sys_user ADD role_id INTEGER",
                "ALTER TABLE sys_user ADD avatar_url VARCHAR(255)",
                "ALTER TABLE sys_user ADD create_time DATETIME",
                "ALTER TABLE sys_user ADD update_time DATETIME",
                "CREATE TABLE student_info (user_id INTEGER, class_teacher_id INTEGER)",
            ):
                db.execute(text(query))
            refresh_tokens.create(db.connection())
            session_kids.create(db.connection())
            db.execute(roles.insert().values(id=1, role_code="employee", role_name="员工"))
            db.execute(role_permissions.insert().values(role_id=1, permission="dashboard:read"))
            db.execute(roles.insert().values(id=2, role_code="admin", role_name="管理员"))
            db.execute(role_permissions.insert().values(role_id=2, permission="users:manage"))
            db.execute(text(
                "INSERT INTO sys_user(id,username,password_hash,real_name,user_type,status,role_id) "
                "VALUES(4,'reset-admin-test',:password,'管理员','admin','normal',2)"
            ), {"password": hash_password("synthetic-admin-password")})
            db.execute(text(
                "INSERT INTO sys_user(id,username,password_hash,real_name,user_type,status,role_id) "
                "VALUES(3,'base-test',:password,'员工','employee','normal',1)"
            ), {"password": hash_password("synthetic-password")})
            db.commit()

        origin = {"Origin": "https://portal.example.test"}
        credentials = {"username": "base-test", "password": "synthetic-password"}
        with TestClient(app, base_url=origin["Origin"]) as client:
            assert client.post("/api/v1/auth/login", json=credentials).status_code == 403
            login = client.post("/api/v1/auth/login", headers=origin, json=credentials)
            assert login.status_code == 200
            cookies = login.headers.get_list("set-cookie")
            assert any("__Secure-edu_refresh=" in line and "HttpOnly" in line and "Secure" in line for line in cookies)
            assert any("__Host-edu_csrf=" in line and "Path=/" in line and "Secure" in line for line in cookies)
            old = client.cookies["__Secure-edu_refresh"]
            csrf = client.cookies["__Host-edu_csrf"]
            headers = {**origin, "X-CSRF-Token": csrf}
            assert client.post("/api/v1/auth/refresh", headers=origin).status_code == 403
            assert client.get("/api/v1/auth/refresh").status_code == 405
            refreshed = client.post("/api/v1/auth/refresh", headers=headers)
            assert refreshed.status_code == 200
            assert client.cookies["__Secure-edu_refresh"] != old
            token = refreshed.json()["data"]["access_token"]
            access = {"Authorization": "Bearer " + token}
            assert client.get("/api/v1/auth/me", headers=access).status_code == 200
            with TestClient(app, base_url=origin["Origin"]) as replay:
                replay.cookies.set("__Secure-edu_refresh", old)
                replay.cookies.set("__Host-edu_csrf", csrf)
                assert replay.post("/api/v1/auth/refresh", headers=headers).status_code == 401
            assert client.get("/api/v1/auth/me", headers=access).status_code == 401
            assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
            assert "__Secure-edu_refresh" not in client.cookies

            employee_login = client.post("/api/v1/auth/login", headers=origin, json=credentials)
            employee_access = {"Authorization": "Bearer " + employee_login.json()["data"]["access_token"]}
            employee_csrf = {**origin, "X-CSRF-Token": client.cookies["__Host-edu_csrf"]}
            reset = "/api/v1/auth/users/3/password"
            next_password = {"new_password": "synthetic-new-password"}
            assert client.post(reset, headers=employee_access, json=next_password).status_code == 403

            with TestClient(app, base_url=origin["Origin"]) as admin:
                login = admin.post("/api/v1/auth/login", headers=origin, json={
                    "username": "reset-admin-test", "password": "synthetic-admin-password",
                })
                admin_access = {"Authorization": "Bearer " + login.json()["data"]["access_token"]}
                invalid = admin.post(reset, headers=admin_access, json={"new_password": "secret123"})
                assert invalid.status_code == 422 and "secret123" not in invalid.text
                assert admin.post(reset, headers=admin_access, json=next_password).json()["data"] == {
                    "id": 3, "sessions_revoked": True,
                }
                assert admin.get("/api/v1/auth/me", headers=admin_access).status_code == 200

            assert client.get("/api/v1/auth/me", headers=employee_access).status_code == 401
            assert client.post("/api/v1/auth/refresh", headers=employee_csrf).status_code == 401
            assert client.post("/api/v1/auth/login", headers=origin, json=credentials).status_code == 401
            assert client.post("/api/v1/auth/login", headers=origin, json={
                **credentials, "password": next_password["new_password"],
            }).status_code == 200
    finally:
        engine.dispose()
