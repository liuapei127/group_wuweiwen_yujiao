"""Initialize a fresh local MySQL test database and generate private demo credentials."""
import argparse
import json
import os
from pathlib import Path
import re
from uuid import uuid4

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from app.core.config import get_settings
from app.core.security.credentials import hash_password
from app.core.security.rbac import ROLE_DEFAULTS

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "migrations" / "local_integration_schema.sql"
ROLE_LABELS = {
    "admin": "联调管理员",
    "employee": "联调顾问",
    "manager": "联调主管",
    "team_leader": "联调班主任",
    "student": "学生",
}
DEMO_MOBILES = {
    "admin": "19900001101",
    "employee": "19900001102",
    "manager": "19900001103",
    "team_leader": "19900001104",
}
DEMO_GRANTS = {
    "employee": {"visitor-intake:read", "visitor-intake:write"},
    "manager": {"visitor-intake:read", "visitor-intake:write", "reports:summary:read",
                "reports:operations:read", "reports:formal:generate"},
    "team_leader": {"student-alerts:read", "student-alerts:write", "academics:read",
                    "academics:write", "applications:read", "applications:write"},
}


def read_ddl(path=SCHEMA):
    delimiter = ";"
    buffer = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        if stripped.startswith("DELIMITER "):
            if buffer:
                raise ValueError("Unexpected delimiter in schema")
            delimiter = stripped.split()[1]
            continue
        buffer.append(line)
        if stripped.endswith(delimiter):
            yield chr(10).join(buffer).rstrip()[:-len(delimiter)]
            buffer.clear()
    if buffer:
        raise ValueError("Unterminated statement in schema")


def seed_accounts(conn):
    accounts = []
    for role_code, name in ROLE_LABELS.items():
        role_id = conn.execute(
            text("INSERT INTO sys_role (role_code,role_name) VALUES (:code,:name)"),
            {"code": role_code, "name": name},
        ).lastrowid
        grants = sorted(ROLE_DEFAULTS[role_code] | DEMO_GRANTS.get(role_code, set()))
        if grants:
            conn.execute(text("INSERT INTO ent_auth_role_permission (role_id,permission) VALUES (:role_id,:permission)"),
                         [{"role_id": role_id, "permission": permission} for permission in grants])
        if role_code == "student":
            continue
        username = DEMO_MOBILES[role_code]
        password = username[-6:]
        user_id = conn.execute(text(
            "INSERT INTO sys_user (username,password_hash,real_name,user_type,role_id,contact_info) "
            "VALUES (:username,:password_hash,:name,:user_type,:role_id,:username)"
        ), {"username": username, "password_hash": hash_password(password), "name": name,
            "user_type": "admin" if role_code == "admin" else "employee", "role_id": role_id}).lastrowid
        accounts.append({"username": username, "password": password, "role": role_code, "id": user_id})
    ids = {row["role"]: row["id"] for row in accounts}
    org_id = conn.execute(text(
        "INSERT INTO sys_organization (org_name,org_level,manager_id,sort_order,status,create_time,update_time) "
        "VALUES ('本机联调组织',1,:manager_id,0,1,UTC_TIMESTAMP(),UTC_TIMESTAMP())"
    ), {"manager_id": ids["manager"]}).lastrowid
    conn.execute(text("SET @base_org_actor_user_id = :admin_id"), {"admin_id": ids["admin"]})
    try:
        conn.execute(text(
            "INSERT INTO sys_org_member (user_id,org_id,status,effective_from) "
            "VALUES (:user_id,:org_id,'active',UTC_TIMESTAMP())"
        ), [{"user_id": ids[role], "org_id": org_id} for role in ("employee", "team_leader")])
    finally:
        conn.execute(text("SET @base_org_actor_user_id = NULL"))
    return accounts


def write_private_json(path, data):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(data, stream, ensure_ascii=False, indent=2)
        stream.write(chr(10))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", required=True)
    args = parser.parse_args()
    settings = get_settings()
    if settings.db_host not in ("127.0.0.1", "localhost", "::1"):
        parser.error("Use a local MySQL server")
    if not re.fullmatch(r"education_service_test(?:_[a-zA-Z0-9_]+)?", settings.db_name):
        parser.error("Use a dedicated database named education_service_test or education_service_test_<name>")

    logs = ROOT / "logs"
    logs.mkdir(exist_ok=True)
    key_path = logs / f"{settings.db_name}-rs256.key"
    credential_path = logs / f"{settings.db_name}-credentials.json"
    if key_path.exists() or credential_path.exists():
        parser.error("Local credential files already exist. Use a fresh database name for a separate setup.")

    engine = create_engine(URL.create("mysql+pymysql", username=settings.db_user, password=settings.db_password,
                                      host=settings.db_host, port=settings.db_port, database=settings.db_name))
    try:
        with engine.connect() as conn:
            if conn.scalar(text("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()")):
                parser.error("The target test database must be empty")
            for ddl in read_ddl():
                conn.exec_driver_sql(ddl)
            conn.commit()
        with engine.begin() as conn:
            accounts = seed_accounts(conn)
        with engine.connect() as conn:
            for migration in ("014_student_assistant.sql", "015_reporting_board.sql", "016_website_content.sql", "017_customer_chat_session.sql", "018_visitor_avatar.sql", "019_event_publication.sql", "020_visitor_nickname.sql", "021_customer_workspace.sql"):
                for ddl in read_ddl(SCHEMA.parent / "pending" / migration):
                    conn.exec_driver_sql(ddl)
            conn.commit()
    finally:
        engine.dispose()

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                    serialization.NoEncryption()).decode("ascii")
    public_pem = key.public_key().public_bytes(serialization.Encoding.PEM,
                                             serialization.PublicFormat.SubjectPublicKeyInfo).decode("ascii")
    write_private_json(key_path, [{"kid": "local-" + uuid4().hex, "status": "active",
                                 "private_pem": private_pem, "public_pem": public_pem}])
    write_private_json(credential_path, {"accounts": accounts})
    print(f"Test database: {settings.db_name}")
    print(f"Set BASE_JWT_KEYS_FILE to: {key_path}")
    print(f"Local test accounts: {credential_path}")


if __name__ == "__main__":
    main()
