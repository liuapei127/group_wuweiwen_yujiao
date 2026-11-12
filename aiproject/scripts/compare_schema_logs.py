"""输出本地 education_service 与 db_init 标准 CRM 表结构对比日志（不含密码）。"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv
import os

ROOT = Path(__file__).resolve().parents[1]
SQL_FILE = ROOT.parent / "教育服务_0914" / "2222通过表可以实现curd" / "db_init.sql"
OUT = ROOT / "docs" / "提交GPT编号" / "12-附录-结构对比与安装日志片段.txt"


def parse_create_columns(sql: str, table: str) -> list[str]:
    m = re.search(
        rf"CREATE TABLE `{table}`\s*\((.*?)\)\s*ENGINE",
        sql,
        re.DOTALL | re.IGNORECASE,
    )
    if not m:
        return []
    cols: list[str] = []
    for line in m.group(1).splitlines():
        line = line.strip().rstrip(",")
        if not line or line.upper().startswith(("PRIMARY", "KEY", "UNIQUE", "CONSTRAINT")):
            continue
        col = line.split()[0].strip("`")
        cols.append(col)
    return cols


def main() -> int:
    load_dotenv(ROOT / ".env")
    sql_text = SQL_FILE.read_text(encoding="utf-8-sig")
    conn = pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "education_service"),
        charset="utf8mb4",
    )
    lines: list[str] = []
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()"
            )
            lines.append(f"table_count={cur.fetchone()[0]}")
            cur.execute("SHOW TABLES")
            tables = sorted(r[0] for r in cur.fetchall())
            lines.append("tables=" + ",".join(tables))
            for tbl in ("crm_lead", "crm_follow_up"):
                cur.execute(f"SHOW CREATE TABLE `{tbl}`")
                ddl = cur.fetchone()[1]
                lines.append(f"\n--- SHOW CREATE TABLE {tbl} ---\n{ddl}\n")
                cur.execute(
                    "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
                    "WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION",
                    (tbl,),
                )
                db_cols = [r[0] for r in cur.fetchall()]
                std_cols = parse_create_columns(sql_text, tbl)
                missing = [c for c in std_cols if c not in db_cols]
                extra = [c for c in db_cols if c not in std_cols]
                lines.append(f"{tbl}_std_columns={std_cols}")
                lines.append(f"{tbl}_db_columns={db_cols}")
                lines.append(f"{tbl}_missing_vs_std={missing or 'none'}")
                lines.append(f"{tbl}_extra_vs_std={extra or 'none'}")
    finally:
        conn.close()

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    ok = "table_count=31" in lines[0] and "missing_vs_std=none" in "\n".join(lines)
    return 0 if ok else 2


if __name__ == "__main__":
    raise SystemExit(main())
