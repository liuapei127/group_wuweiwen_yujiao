"""真实 HTTP + Uvicorn 客户管理 E2E（需 .env 中 DB_* 与 AUTH_BEARER_TOKEN）。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

import httpx
import pymysql

ROOT = Path(__file__).resolve().parents[1]
MARKER = f"E2E_HTTP_{datetime.now().strftime('%Y%m%d_%H%M%S')}"


def load_env_file() -> None:
    env_path = ROOT / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


def db_verify(remark: str) -> list[dict]:
    conn = pymysql.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "education_service"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, status, owner_employee_id, remark FROM crm_lead WHERE remark=%s ORDER BY id DESC LIMIT 1",
                (remark,),
            )
            return list(cur.fetchall())
    finally:
        conn.close()


def main() -> int:
    load_env_file()
    os.chdir(ROOT)
    token = os.environ.get("AUTH_BEARER_TOKEN", "")
    if not token:
        print("BLOCKER: AUTH_BEARER_TOKEN 未配置，无法做真实 HTTP 业务验收（503/401）")
        return 2

    auth_headers = {
        "Authorization": f"Bearer {token}",
        "X-Employee-Id": "1",
        "Content-Type": "application/json",
    }
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8765"],
        cwd=ROOT,
        env=os.environ.copy(),
    )
    base = "http://127.0.0.1:8765"
    log = []
    lead_id = None
    try:
        for _ in range(30):
            try:
                r = httpx.get(f"{base}/health/db", timeout=2)
                if r.status_code == 200:
                    break
            except Exception:
                time.sleep(0.3)
        else:
            print("uvicorn start timeout")
            return 1

        r = httpx.post(
            f"{base}/api/v1/consultant/leads",
            headers=auth_headers,
            json={
                "customer_name": f"HTTP测评{MARKER}",
                "contact_info": "13900009999",
                "owner_employee_id": 1,
                "remark": MARKER,
                "intended_country": "德国",
            },
            timeout=10,
        )
        log.append({"step": "create", "status": r.status_code, "body": r.json()})
        if r.status_code == 200 and r.json().get("code") == 0:
            lead_id = r.json()["data"]["id"]

        r2 = httpx.get(
            f"{base}/api/v1/consultant/leads",
            headers=auth_headers,
            params={"keyword": MARKER},
            timeout=10,
        )
        log.append({"step": "list", "status": r2.status_code, "body": r2.json()})

        if lead_id:
            r3 = httpx.get(f"{base}/api/v1/consultant/leads/{lead_id}", headers=auth_headers, timeout=10)
            log.append({"step": "detail", "status": r3.status_code, "body": r3.json()})
            r4 = httpx.patch(
                f"{base}/api/v1/consultant/leads/{lead_id}/status",
                headers=auth_headers,
                json={"status": "contacting"},
                timeout=10,
            )
            log.append({"step": "status", "status": r4.status_code, "body": r4.json()})
            r5 = httpx.get(f"{base}/api/v1/consultant/leads/{lead_id}", headers=auth_headers, timeout=10)
            log.append({"step": "detail_after", "status": r5.status_code, "body": r5.json()})

        r401 = httpx.post(
            f"{base}/api/v1/consultant/leads",
            json={"customer_name": "x", "owner_employee_id": 1},
            timeout=10,
        )
        log.append({"step": "unauth_create", "status": r401.status_code, "body": r401.text[:200]})

        rows = db_verify(MARKER) if lead_id else []
        out = {"marker": MARKER, "lead_id": lead_id, "http_steps": log, "db_rows": rows}
        out_path = ROOT / "docs" / "客户管理-HTTP-E2E测试记录.md"
        out_path.write_text(
            f"# 客户管理 HTTP E2E\n\n时间：{datetime.now().isoformat()}\n\n```json\n"
            + json.dumps(out, ensure_ascii=False, indent=2)
            + "\n```\n",
            encoding="utf-8",
        )
        print(json.dumps(out, ensure_ascii=False, indent=2))
        ok = lead_id and rows and rows[0].get("status") == "contacting" and r401.status_code in (401, 503)
        return 0 if ok else 1
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == "__main__":
    raise SystemExit(main())
