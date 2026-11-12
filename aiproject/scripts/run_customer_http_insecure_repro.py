"""漏洞复现：启动 tests.repro.asgi_app，不等于安全验收。security_acceptance=FAIL。"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pymysql

ROOT = Path(__file__).resolve().parents[1]
MARKER = f"E2E_REPRO_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
RUN_ID = uuid.uuid4().hex[:12]

REQUIRED = (
    "create_has_id",
    "create_owner_and_status",
    "emp2_status_403",
    "emp2_no_side_effect",
    "spoof_repro",
)


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


def pick_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def db_lead_snapshot(lead_id: int) -> dict | None:
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
                "SELECT id, status, owner_employee_id, remark FROM crm_lead WHERE id=%s",
                (lead_id,),
            )
            return cur.fetchone()
    finally:
        conn.close()


def add_result(results: list, name: str, outcome: str, **fields: Any) -> None:
    results.append({"case": name, "outcome": outcome, **fields})


def main() -> int:
    started_at = datetime.now(timezone.utc).astimezone().isoformat()
    load_env_file()
    token = os.environ.get("AUTH_BEARER_TOKEN", "")
    if not token:
        print("BLOCKER: AUTH_BEARER_TOKEN")
        return 2

    port = pick_port()
    env = os.environ.copy()
    env.pop("EMPLOYEE_IDENTITY_MODE", None)
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "tests.repro.asgi_app:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=ROOT,
        env=env,
    )
    base = f"http://127.0.0.1:{port}"
    results: list[dict] = []
    lead_id: int | None = None
    exit_code = 1
    try:
        if proc.poll() is not None:
            add_result(results, "server_start", "BLOCKED", reason="process exited early")
        else:
            ready = False
            for _ in range(40):
                if proc.poll() is not None:
                    break
                try:
                    if httpx.get(f"{base}/health/db", timeout=2).status_code == 200:
                        ready = True
                        break
                except Exception:
                    time.sleep(0.25)
            if not ready:
                add_result(results, "server_ready", "BLOCKED", port=port)
            else:
                h1 = {
                    "Authorization": f"Bearer {token}",
                    "X-Employee-Id": "1",
                    "Content-Type": "application/json",
                }
                r = httpx.post(
                    f"{base}/api/v1/consultant/leads",
                    headers=h1,
                    json={
                        "customer_name": f"repro{MARKER}",
                        "contact_info": "13900008888",
                        "owner_employee_id": 1,
                        "remark": MARKER,
                    },
                    timeout=15,
                )
                body = r.json() if "application/json" in r.headers.get("content-type", "") else {}
                lead_id = body.get("data", {}).get("id") if isinstance(body, dict) else None
                ok_create = (
                    r.status_code == 200
                    and isinstance(body, dict)
                    and body.get("code") == 0
                    and lead_id
                )
                add_result(
                    results,
                    "create_has_id",
                    "PASS" if ok_create else "FAIL",
                    http_status=r.status_code,
                    lead_id=lead_id,
                )
                if lead_id:
                    snap0 = db_lead_snapshot(lead_id)
                    ok0 = (
                        snap0
                        and snap0.get("status") == "new"
                        and snap0.get("owner_employee_id") == 1
                        and snap0.get("remark") == MARKER
                    )
                    add_result(
                        results,
                        "create_owner_and_status",
                        "PASS" if ok0 else "FAIL",
                        snapshot=snap0,
                    )

                    snap_before = db_lead_snapshot(lead_id)
                    h2 = {**h1, "X-Employee-Id": "2"}
                    r403 = httpx.patch(
                        f"{base}/api/v1/consultant/leads/{lead_id}/status",
                        headers=h2,
                        json={"status": "contacting"},
                        timeout=15,
                    )
                    snap_after_403 = db_lead_snapshot(lead_id)
                    add_result(
                        results,
                        "emp2_status_403",
                        "PASS" if r403.status_code == 403 else "FAIL",
                        actual=r403.status_code,
                    )
                    add_result(
                        results,
                        "emp2_no_side_effect",
                        "PASS" if snap_before == snap_after_403 else "FAIL",
                    )

                    snap_pre_spoof = db_lead_snapshot(lead_id)
                    r_spoof = httpx.patch(
                        f"{base}/api/v1/consultant/leads/{lead_id}/status",
                        headers=h1,
                        json={"status": "contacting"},
                        timeout=15,
                    )
                    snap_post = db_lead_snapshot(lead_id)
                    body_s = r_spoof.json() if "application/json" in r_spoof.headers.get("content-type", "") else {}
                    repro_ok = (
                        r_spoof.status_code == 200
                        and isinstance(body_s, dict)
                        and body_s.get("code") == 0
                        and snap_pre_spoof
                        and snap_post
                        and snap_pre_spoof.get("status") == "new"
                        and snap_post.get("status") == "contacting"
                        and snap_post.get("owner_employee_id") == 1
                        and snap_post.get("remark") == MARKER
                    )
                    add_result(
                        results,
                        "spoof_repro",
                        "KNOWN_DEFECT" if repro_ok else ("NOT_REPRODUCED" if r_spoof.status_code == 503 else "FAIL"),
                        security_expected="reject",
                        repro_http=r_spoof.status_code,
                        before=snap_pre_spoof,
                        after=snap_post,
                    )

    finally:
        proc.terminate()
        proc.wait(timeout=15)

    finished_at = datetime.now(timezone.utc).astimezone().isoformat()
    missing = [c for c in REQUIRED if c not in {r["case"] for r in results}]
    for c in missing:
        add_result(results, c, "BLOCKED", reason="not executed")

    failures = [r for r in results if r["outcome"] in ("FAIL", "BLOCKED")]
    known = [r for r in results if r["outcome"] == "KNOWN_DEFECT"]
    all_required_pass = all(
        r["outcome"] in ("PASS", "KNOWN_DEFECT")
        for r in results
        if r["case"] in REQUIRED
    )
    exit_code = 0 if all_required_pass and not failures else 1

    out = {
        "run_id": RUN_ID,
        "suite": "tests.repro.asgi_app",
        "security_acceptance": "FAIL",
        "marker": MARKER,
        "lead_id": lead_id,
        "port": port,
        "python": sys.version.split()[0],
        "started_at": started_at,
        "finished_at": finished_at,
        "required_cases": list(REQUIRED),
        "results": results,
        "known_defects": len(known),
        "exit_code": exit_code,
    }
    runs_dir = ROOT / "docs" / "回复Cursor" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    body = (
        f"# 漏洞复现（tests.repro.asgi_app）\n\n"
        f"run_id=`{RUN_ID}` · security_acceptance=**FAIL**\n\n"
        f"```json\n{json.dumps(out, ensure_ascii=False, indent=2)}\n```\n"
    )
    (runs_dir / f"17-repro-{RUN_ID}.md").write_text(body, encoding="utf-8")
    (ROOT / "docs" / "回复Cursor" / "17-HTTP漏洞复现-insecure.md").write_text(body, encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
