"""从 14 号 JSON 导出 CRM 结构表（库侧实测值）；结论列不自动生成。"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "docs" / "回复Cursor" / "14-CRM结构完整对比.json"
STD = ROOT.parent / "教育服务_0914" / "2222通过表可以实现curd" / "db_init.sql"
OUT = ROOT / "docs" / "回复Cursor" / "19-CRM结构导出表-自14快照.md"


def fmt_default(c: dict) -> str:
    d = c.get("COLUMN_DEFAULT")
    if d is None:
        return "NULL（可空）" if c.get("IS_NULLABLE") == "YES" else "无显式默认"
    return str(d)


def col_row(c: dict) -> str:
    return (
        f"| `{c['COLUMN_NAME']}` | `{c['COLUMN_TYPE']}` | {c['IS_NULLABLE']} | "
        f"{fmt_default(c)} | {c['EXTRA'] or '—'} | 待核对 |"
    )


def index_rows(indexes: list[dict]) -> list[str]:
    lines = ["| Key | 唯一 | 列序 | 列名 | 结论 |", "| --- | --- | --- | --- | --- |"]
    for idx in indexes:
        uniq = "否" if idx.get("Non_unique") else "是"
        lines.append(
            f"| {idx['Key_name']} | {uniq} | {idx['Seq_in_index']} | {idx['Column_name']} | 待核对 |"
        )
    return lines


def main() -> int:
    data = json.loads(SRC.read_text(encoding="utf-8"))
    std_hash = hashlib.sha256(STD.read_bytes()).hexdigest() if STD.is_file() else "missing"
    now = datetime.now(timezone.utc).astimezone().isoformat()
    parts = [
        "# 19 · CRM 结构导出表（自 14 号数据库快照）",
        "",
        "> **本文件为结构数据导出，不含自动 diff 结论。** 人工核对结论见 `19-CRM人工核对结论.md`。",
        "",
        f"- 快照来源：`14-CRM结构完整对比.json`",
        f"- 导出时间：{now}",
        f"- 标准 SQL 字节 SHA256：`{std_hash}`",
        f"- 库名：`{data.get('database')}`",
        "- 结论列固定为 **待核对**（由导出脚本写入，不代表已比较）",
        "",
    ]
    for table in ("crm_lead", "crm_follow_up"):
        t = data["tables"][table]
        parts.append(f"## `{table}`")
        parts.append("")
        parts.append("| 列 | TYPE | NULL | DEFAULT（表述） | EXTRA | 结论 |")
        parts.append("| --- | --- | --- | --- | --- | --- |")
        for c in t["columns_db"]:
            parts.append(col_row(c))
        parts.append("")
        parts.extend(index_rows(t["indexes_db"]))
        parts.append("")
        parts.append("表字符集/排序：见 14 号 `show_create`")
        parts.append("")
    OUT.write_text("\n".join(parts), encoding="utf-8")
    print(f"written {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
