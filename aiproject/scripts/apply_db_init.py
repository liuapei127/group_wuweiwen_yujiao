"""Apply 教育服务 db_init.sql to local MySQL (all 31 tables)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
SQL_FILE = REPO / "教育服务_0914" / "2222通过表可以实现curd" / "db_init.sql"


def main() -> int:
    load_dotenv(ROOT / ".env")
    host = os.getenv("DB_HOST", "127.0.0.1")
    port = int(os.getenv("DB_PORT", "3306"))
    user = os.getenv("DB_USER", "root")
    password = os.getenv("DB_PASSWORD", "")
    db_name = os.getenv("DB_NAME", "education_service")

    if not SQL_FILE.is_file():
        print(f"SQL file not found: {SQL_FILE}", file=sys.stderr)
        return 1

    sql_text = SQL_FILE.read_text(encoding="utf-8-sig")
    lines = [ln for ln in sql_text.splitlines() if not ln.lstrip().startswith("--")]
    body = "\n".join(lines)
    statements: list[str] = []
    for part in body.split(";"):
        stmt = part.strip()
        if stmt:
            statements.append(stmt)

    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        autocommit=True,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                f"CREATE DATABASE IF NOT EXISTS `{db_name}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            cur.execute(f"USE `{db_name}`")
            for stmt in statements:
                if stmt.upper().startswith("SET NAMES"):
                    cur.execute(stmt)
                    continue
                cur.execute(stmt)
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables "
                "WHERE table_schema = %s",
                (db_name,),
            )
            count = cur.fetchone()[0]
            cur.execute("SHOW TABLES")
            tables = [row[0] for row in cur.fetchall()]
    finally:
        conn.close()

    print(f"Database: {db_name}")
    print(f"Tables: {count}")
    for name in sorted(tables):
        print(f"  - {name}")
    return 0 if count == 31 else 2


if __name__ == "__main__":
    raise SystemExit(main())
