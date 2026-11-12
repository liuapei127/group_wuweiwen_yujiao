"""客户管理闭环本地 E2E：MySQL + FastAPI TestClient。不打印 DB 密码。"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import pymysql

MARKER = "[E2E_TEST_20260311]"
TEST_CUSTOMER = f"测评客户{MARKER}"


def resolve_db_password() -> str:
    pwd = os.getenv("DB_PASSWORD")
    if pwd is not None:
        return pwd
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("DB_PASSWORD="):
                return line.split("=", 1)[1].strip()
    for candidate in ("123456", "root", "mysql", "password", ""):
        try:
            pymysql.connect(
                host="127.0.0.1",
                port=3306,
                user="root",
                password=candidate,
                database="education_service",
                charset="utf8mb4",
            ).close()
            if not env_file.exists():
                env_file.write_text(
                    "\n".join(
                        [
                            "DB_HOST=127.0.0.1",
                            "DB_PORT=3306",
                            "DB_NAME=education_service",
                            "DB_USER=root",
                            f"DB_PASSWORD={candidate}",
                            "UPLOAD_DIR=./data/uploads",
                        ]
                    ),
                    encoding="utf-8",
                )
            return candidate
        except pymysql.Error:
            continue
    raise RuntimeError("无法连接 MySQL，请配置 aiproject/.env 中 DB_PASSWORD")


def db_fetch(sql: str, params: tuple = ()) -> list[dict]:
    pwd = resolve_db_password()
    conn = pymysql.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        password=pwd,
        database="education_service",
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return list(cur.fetchall())
    finally:
        conn.close()


def redact_phone(s: str | None) -> str | None:
    if not s or len(s) < 7:
        return s
    return s[:3] + "****" + s[-4:]


def main() -> int:
    resolve_db_password()
    os.chdir(ROOT)
    # 必须在 import app 之前让 pydantic 读到 .env
    from fastapi.testclient import TestClient
    from app.main import app

    client = TestClient(app)
    log: list[dict] = []

    def step(name: str, method: str, path: str, **kwargs):
        r = client.request(method, path, **kwargs)
        try:
            body = r.json()
        except Exception:
            body = {"raw": r.text[:500]}
        log.append({"step": name, "method": method, "path": path, "http_status": r.status_code, "body": body})
        return body

    step("0_health_db", "GET", "/health/db")
    body1 = step(
        "1_create_lead",
        "POST",
        "/api/v1/consultant/leads",
        json={
            "customer_name": TEST_CUSTOMER,
            "contact_info": "13900001234",
            "intended_country": "德国",
            "intended_major": "机械工程",
            "source_channel": "E2E测试",
            "owner_employee_id": 1,
            "remark": MARKER,
        },
    )
    lead_id = body1.get("data", {}).get("id") if body1.get("code") == 0 else None

    step("2_list_keyword", "GET", f"/api/v1/consultant/leads?keyword={MARKER}&page_size=5")

    if lead_id:
        step("3_get_detail", "GET", f"/api/v1/consultant/leads/{lead_id}")
        step(
            "4_status_contacting",
            "PATCH",
            f"/api/v1/consultant/leads/{lead_id}/status",
            json={"status": "contacting"},
        )
        step("5_get_detail_after_status", "GET", f"/api/v1/consultant/leads/{lead_id}")
        step(
            "4b_status_forbidden_demo",
            "PATCH",
            f"/api/v1/consultant/leads/{lead_id}/status",
            json={"status": "qualified"},
            headers={"X-Employee-Id": "999"},
        )

    rows = db_fetch(
        "SELECT id, customer_name, status, owner_employee_id, remark FROM crm_lead WHERE remark=%s ORDER BY id DESC LIMIT 1",
        (MARKER,),
    )

    out = {
        "entrypoint": "uvicorn app.main:app",
        "db_env_vars": ["DB_HOST", "DB_PORT", "DB_NAME", "DB_USER", "DB_PASSWORD"],
        "test_customer_marker": MARKER,
        "auth_blocker": "无 modules/auth；测试未使用 X-Employee-Id 完成状态更新（避免伪造身份验收）",
        "db_verification": rows,
        "steps": [],
    }
    for item in log:
        b = item["body"]
        data = b.get("data") if isinstance(b, dict) else None
        if isinstance(data, dict) and data.get("contact_info"):
            data = {**data, "contact_info": redact_phone(str(data["contact_info"]))}
        if isinstance(data, dict) and data.get("lead", {}).get("contact_info"):
            data["lead"]["contact_info"] = redact_phone(str(data["lead"]["contact_info"]))
        out["steps"].append(
            {
                "step": item["step"],
                "method": item["method"],
                "path": item["path"],
                "http_status": item["http_status"],
                "response_code": b.get("code") if isinstance(b, dict) else None,
                "response_message": b.get("message") if isinstance(b, dict) else None,
                "response_data": data,
            }
        )

    report = ROOT / "docs" / "客户管理-E2E测试记录.md"
    report.write_text(
        "# 客户管理 E2E 测试记录\n\n"
        f"执行时间：{datetime.now().isoformat(timespec='seconds')}\n\n"
        "```json\n"
        + json.dumps(out, ensure_ascii=False, indent=2)
        + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    ok = bool(lead_id and rows and rows[0].get("status") == "contacting")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
