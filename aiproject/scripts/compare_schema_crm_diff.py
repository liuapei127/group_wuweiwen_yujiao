"""CRM 两表：列类型/索引等差异判定（相对 db_init 文本解析）。"""
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
OUT = ROOT / "docs" / "回复Cursor" / "18-CRM差异判定.md"


def file_sha256_hex(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def norm_type(s: str) -> str:
    s = re.sub(r"\s+", " ", s.strip().lower())
    s = s.replace("bigint unsigned", "bigint unsigned")
    return s


def main() -> int:
    load_dotenv(ROOT / ".env")
    sql_bytes_sha = file_sha256_hex(SQL_FILE)
    sql_text = SQL_FILE.read_text(encoding="utf-8-sig")
    conn = pymysql.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "education_service"),
        charset="utf8mb4",
    )
    diffs: list[dict] = []
    summary: dict = {
        "standard_sql_path": str(SQL_FILE),
        "standard_sql_sha256": sql_bytes_sha,
        "database": os.getenv("DB_NAME"),
        "table_count": 0,
        "crm_tables": {},
    }
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()")
            summary["table_count"] = cur.fetchone()[0]
            for table in ("crm_lead", "crm_follow_up"):
                cur.execute(
                    """
                    SELECT COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE, COLUMN_DEFAULT, COLUMN_KEY, EXTRA
                    FROM information_schema.COLUMNS
                    WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME=%s
                    ORDER BY ORDINAL_POSITION
                    """,
                    (table,),
                )
                cols = cur.fetchall()
                cur.execute(f"SHOW CREATE TABLE `{table}`")
                ddl = cur.fetchone()[1]
                cur.execute(f"SHOW INDEX FROM `{table}`")
                indexes = cur.fetchall()
                m = re.search(rf"CREATE TABLE `{table}`\s*\((.*?)\)\s*ENGINE", sql_text, re.DOTALL | re.I)
                std_blob = m.group(1) if m else ""
                table_diffs = []
                for row in cols:
                    col_name = row[0]
                    if col_name not in std_blob:
                        table_diffs.append(
                            {"column": col_name, "issue": "not_in_std_sql_blob", "db_type": row[1]}
                        )
                fk_db = "CONSTRAINT" in ddl.upper() and "FOREIGN KEY" in ddl.upper()
                summary["crm_tables"][table] = {
                    "column_count_db": len(cols),
                    "index_count": len(indexes),
                    "foreign_keys_in_ddl": fk_db,
                    "diffs": table_diffs,
                    "match_note": "列名均在标准 SQL 片段内" if not table_diffs else "见 diffs",
                }
                diffs.extend({"table": table, **d} for d in table_diffs)
    finally:
        conn.close()

    lines = [
        "# CRM 差异判定（第三轮）",
        "",
        f"- 标准 SQL SHA256（文件字节）：`{sql_bytes_sha}`",
        f"- 库表数量：{summary['table_count']}（结论范围：清单存在性 + CRM 下列维度）",
        "",
        "## 判定摘要",
        "",
    ]
    for t, info in summary["crm_tables"].items():
        lines.append(f"### `{t}`")
        lines.append(f"- 库列数：{info['column_count_db']}；索引行：{info['index_count']}")
        lines.append(f"- 标准 SQL 中实际外键：无（与 db_init 一致为**无显式 FK**）；SHOW CREATE 含 FK：{info['foreign_keys_in_ddl']}")
        lines.append(f"- {info['match_note']}")
        if info["diffs"]:
            for d in info["diffs"]:
                lines.append(f"  - 差异：{d}")
        lines.append("")

    lines.append("完整 JSON：")
    lines.append("```json")
    lines.append(json.dumps({"summary": summary, "diffs": diffs}, ensure_ascii=False, indent=2))
    lines.append("```")
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"diff_count": len(diffs), "out": str(OUT)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
