"""CRM 两表：列级完整维度对比（information_schema vs db_init 解析）。"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pymysql
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parents[1]
SQL_FILE = ROOT.parent / "教育服务_0914" / "2222通过表可以实现curd" / "db_init.sql"
OUT_JSON = ROOT / "docs" / "回复Cursor" / "14-CRM结构完整对比.json"


def parse_columns_from_sql(sql: str, table: str) -> dict[str, dict[str, str]]:
    m = re.search(rf"CREATE TABLE `{table}`\s*\((.*?)\)\s*ENGINE", sql, re.DOTALL | re.IGNORECASE)
    if not m:
        return {}
    cols: dict[str, dict[str, str]] = {}
    for line in m.group(1).splitlines():
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith(("PRIMARY", "KEY", "UNIQUE", "CONSTRAINT")):
            continue
        parts = line.split()
        name = parts[0].strip("`")
        cols[name] = {"raw": line}
    return cols


def fetch_db_columns(cur, table: str) -> list[dict]:
    cur.execute(
        """
        SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_KEY, EXTRA,
               CHARACTER_SET_NAME, COLLATION_NAME
        FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s
        ORDER BY ORDINAL_POSITION
        """,
        (table,),
    )
    fields = [d[0] for d in cur.description]
    return [dict(zip(fields, row)) for row in cur.fetchall()]


def fetch_indexes(cur, table: str) -> list[dict]:
    cur.execute(f"SHOW INDEX FROM `{table}`")
    fields = [d[0] for d in cur.description]
    return [dict(zip(fields, row)) for row in cur.fetchall()]


def main() -> int:
    load_dotenv(ROOT / ".env")
    sql_text = SQL_FILE.read_text(encoding="utf-8-sig")
    sql_hash = hashlib.sha256(sql_text.encode("utf-8")).hexdigest()[:16]
    conn = pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "education_service"),
        charset="utf8mb4",
    )
    report: dict = {
        "standard_sql": str(SQL_FILE),
        "standard_sql_sha256_prefix": sql_hash,
        "database": os.getenv("DB_NAME", "education_service"),
        "scope_note": "31表仅做存在性；CRM两表做下列维度对比",
        "tables": {},
    }
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()")
            report["table_count"] = cur.fetchone()[0]
            for table in ("crm_lead", "crm_follow_up"):
                report["tables"][table] = {
                    "columns_db": fetch_db_columns(cur, table),
                    "indexes_db": fetch_indexes(cur, table),
                    "columns_std_raw": parse_columns_from_sql(sql_text, table),
                }
                cur.execute(f"SHOW CREATE TABLE `{table}`")
                report["tables"][table]["show_create"] = cur.fetchone()[1]
    finally:
        conn.close()

    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"table_count": report["table_count"], "out": str(OUT_JSON)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
