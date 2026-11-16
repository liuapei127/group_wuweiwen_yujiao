"""Create local education_service schema + one website student for manual testing."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pymysql
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL

from app.core.config import get_settings
from app.core.security.credentials import hash_password
from app.core.security.rbac import ROLE_DEFAULTS

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "migrations" / "local_integration_schema.sql"
CREDS = ROOT / "logs" / "local-student-demo-credentials.json"


def read_ddl():
    delimiter = ";"
    buffer: list[str] = []
    for line in SCHEMA.read_text(encoding="utf-8").splitlines():
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
            yield "\n".join(buffer).rstrip()[: -len(delimiter)]
            buffer.clear()
    if buffer:
        raise ValueError("Unterminated statement")


def ensure_database(settings) -> None:
    conn = pymysql.connect(
        host=settings.db_host,
        port=settings.db_port,
        user=settings.db_user,
        password=settings.db_password,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{settings.db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
    finally:
        conn.close()


def ensure_role(conn, code: str, name: str) -> int:
    rid = conn.scalar(text("SELECT id FROM sys_role WHERE role_code=:c"), {"c": code})
    if rid:
        return int(rid)
    return int(
        conn.execute(
            text("INSERT INTO sys_role (role_code, role_name) VALUES (:c,:n)"),
            {"c": code, "n": name},
        ).lastrowid
    )


def ensure_grants(conn, role_id: int, code: str) -> None:
    for permission in sorted(ROLE_DEFAULTS.get(code) or set()):
        exists = conn.scalar(
            text(
                "SELECT 1 FROM ent_auth_role_permission WHERE role_id=:r AND permission=:p"
            ),
            {"r": role_id, "p": permission},
        )
        if not exists:
            conn.execute(
                text(
                    "INSERT INTO ent_auth_role_permission (role_id, permission) VALUES (:r,:p)"
                ),
                {"r": role_id, "p": permission},
            )


def main() -> None:
    settings = get_settings()
    if settings.db_host not in {"127.0.0.1", "localhost", "::1"}:
        raise SystemExit("Only local MySQL is allowed")
    ensure_database(settings)
    engine = create_engine(
        URL.create(
            "mysql+pymysql",
            username=settings.db_user,
            password=settings.db_password,
            host=settings.db_host,
            port=settings.db_port,
            database=settings.db_name,
        )
    )
    with engine.connect() as conn:
        count = conn.scalar(
            text("SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE()")
        )
        if not count:
            for ddl in read_ddl():
                conn.exec_driver_sql(ddl)
            conn.commit()
            print(f"Applied schema to {settings.db_name}")
        else:
            print(f"Reusing existing schema in {settings.db_name} ({count} tables)")

    username = "19900001203"
    password = "StuDemo_123456"
    teacher_user = "19900001105"
    teacher_pass = teacher_user[-6:]

    with engine.begin() as conn:
        student_role = ensure_role(conn, "student", "学生")
        teacher_role = ensure_role(conn, "team_leader", "班主任")
        ensure_grants(conn, student_role, "student")
        ensure_grants(conn, teacher_role, "team_leader")

        teacher_id = conn.scalar(text("SELECT id FROM sys_user WHERE username=:u"), {"u": teacher_user})
        if not teacher_id:
            teacher_id = conn.execute(
                text(
                    "INSERT INTO sys_user "
                    "(username,password_hash,real_name,user_type,role_id,status) "
                    "VALUES (:u,:p,'联调班主任','employee',:r,'normal')"
                ),
                {"u": teacher_user, "p": hash_password(teacher_pass), "r": teacher_role},
            ).lastrowid

        student_id = conn.scalar(
            text("SELECT id FROM sys_user WHERE username=:u"), {"u": "stu_archive_demo"}
        )
        if not student_id:
            student_id = conn.execute(
                text(
                    "INSERT INTO sys_user "
                    "(username,password_hash,real_name,user_type,role_id,status) "
                    "VALUES (:u,:p,'联调学生','student',:r,'normal')"
                ),
                {
                    "u": "stu_archive_demo",
                    "p": hash_password("unused_archive_pw"),
                    "r": student_role,
                },
            ).lastrowid

        if not conn.scalar(text("SELECT id FROM student_info WHERE user_id=:id"), {"id": student_id}):
            conn.execute(
                text(
                    "INSERT INTO student_info (user_id, class_teacher_id, abroad_country, status) "
                    "VALUES (:u,:t,'Germany','active')"
                ),
                {"u": student_id, "t": teacher_id},
            )
        else:
            conn.execute(
                text(
                    "UPDATE student_info SET class_teacher_id=:t, abroad_country='Germany', status='active' "
                    "WHERE user_id=:u"
                ),
                {"u": student_id, "t": teacher_id},
            )

        visitor_id = conn.scalar(
            text("SELECT id FROM visitor_account WHERE username=:u"), {"u": username}
        )
        if not visitor_id:
            visitor_id = conn.execute(
                text(
                    "INSERT INTO visitor_account (username,password_hash,name,contact,created_at) "
                    "VALUES (:u,:p,'联调官网学生','stu_demo@example.invalid',UTC_TIMESTAMP())"
                ),
                {"u": username, "p": hash_password(password)},
            ).lastrowid

        if not conn.scalar(
            text("SELECT visitor_id FROM website_student_access WHERE visitor_id=:v"),
            {"v": visitor_id},
        ):
            conn.execute(
                text(
                    "INSERT INTO website_student_access (visitor_id, student_id, enabled) "
                    "VALUES (:v,:s,1)"
                ),
                {"v": visitor_id, "s": student_id},
            )
        else:
            conn.execute(
                text(
                    "UPDATE website_student_access SET student_id=:s, enabled=1 WHERE visitor_id=:v"
                ),
                {"v": visitor_id, "s": student_id},
            )

    CREDS.parent.mkdir(exist_ok=True)
    payload = {
        "website_login": {"username": username, "password": password},
        "student_archive_username": "stu_archive_demo",
        "teacher": {"username": teacher_user, "password": teacher_pass},
        "urls": {
            "frontend": "http://127.0.0.1:5173/",
            "api_docs": "http://127.0.0.1:8000/docs",
            "dify": "http://127.0.0.1:8090/",
        },
    }
    with engine.connect() as conn:
        payload["student_id"] = int(
            conn.scalar(text("SELECT id FROM sys_user WHERE username='stu_archive_demo'"))
        )
        payload["teacher_id"] = int(
            conn.scalar(text("SELECT id FROM sys_user WHERE username=:u"), {"u": teacher_user})
        )
        payload["visitor_id"] = int(
            conn.scalar(text("SELECT id FROM visitor_account WHERE username=:u"), {"u": username})
        )
    fd = os.open(CREDS, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump(payload, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    print(f"Wrote {CREDS}")
    print(f"Website student login: {username} / {password}")


if __name__ == "__main__":
    main()
