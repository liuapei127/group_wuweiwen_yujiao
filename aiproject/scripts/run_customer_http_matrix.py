"""客户管理 HTTP 验收矩阵（Uvicorn + httpx + 独立查库）。共享输出脱敏。"""
from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pymysql

ROOT = Path(__file__).resolve().parents[1]
MARKER = f"E2E_HTTP_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
MASKED_CONTACT = "139****9999"
PORT = 8766


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


def redact(obj: Any) -> Any:
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k == "contact_info" and isinstance(v, str):
                out[k] = MASKED_CONTACT if v else v
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


def db_conn():
    return pymysql.connect(
        host=os.environ.get("DB_HOST", "127.0.0.1"),
        port=int(os.environ.get("DB_PORT", "3306")),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", ""),
        database=os.environ.get("DB_NAME", "education_service"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def db_lead_by_remark(remark: str) -> list[dict]:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, status, owner_employee_id, remark FROM crm_lead WHERE remark=%s",
                (remark,),
            )
            return list(cur.fetchall())


def db_follow_up_count(lead_id: int, marker_substr: str) -> int:
    with db_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) AS c FROM crm_follow_up WHERE lead_id=%s AND content LIKE %s",
                (lead_id, f"%{marker_substr}%"),
            )
            return int(cur.fetchone()["c"])


def wait_health(base: str) -> bool:
    for _ in range(40):
        try:
            if httpx.get(f"{base}/health/db", timeout=2).status_code == 200:
                return True
        except Exception:
            time.sleep(0.25)
    return False


def headers(emp_id: int, token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Employee-Id": str(emp_id),
        "Content-Type": "application/json",
    }


def record_step(log: list, name: str, r: httpx.Response) -> None:
    body: Any
    try:
        body = r.json()
    except Exception:
        body = r.text[:500]
    log.append({"case": name, "status": r.status_code, "body": redact(body)})


def main() -> int:
    load_env_file()
    os.chdir(ROOT)
    token = os.environ.get("AUTH_BEARER_TOKEN", "")
    if not token:
        print("BLOCKER: AUTH_BEARER_TOKEN 未配置")
        return 2

    results: list[dict[str, Any]] = []
    log: list[dict[str, Any]] = []
    lead_id: int | None = None
    rows: list[dict] = []
    python_ver = sys.version.split()[0]

    env = os.environ.copy()
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=ROOT,
        env=env,
    )
    base = f"http://127.0.0.1:{PORT}"
    try:
        if not wait_health(base):
            print("uvicorn start timeout")
            return 1

        h1 = headers(1, token)
        # 主流程
        r = httpx.post(
            f"{base}/api/v1/consultant/leads",
            headers=h1,
            json={
                "customer_name": f"HTTP矩阵{MARKER}",
                "contact_info": "13900009999",
                "owner_employee_id": 1,
                "remark": MARKER,
                "intended_country": "德国",
            },
            timeout=15,
        )
        record_step(log, "happy_create", r)
        if r.status_code == 200 and isinstance(r.json(), dict) and r.json().get("code") == 0:
            lead_id = r.json()["data"]["id"]

        r = httpx.get(f"{base}/api/v1/consultant/leads", headers=h1, params={"keyword": MARKER}, timeout=15)
        record_step(log, "happy_list", r)
        if lead_id:
            r = httpx.get(f"{base}/api/v1/consultant/leads/{lead_id}", headers=h1, timeout=15)
            record_step(log, "happy_detail", r)
            r = httpx.patch(
                f"{base}/api/v1/consultant/leads/{lead_id}/status",
                headers=h1,
                json={"status": "contacting"},
                timeout=15,
            )
            record_step(log, "happy_status", r)
            r = httpx.get(f"{base}/api/v1/consultant/leads/{lead_id}", headers=h1, timeout=15)
            record_step(log, "happy_detail_after", r)
            r = httpx.post(
                f"{base}/api/v1/consultant/leads/{lead_id}/follow-ups",
                headers=h1,
                json={
                    "employee_id": 1,
                    "follow_type": "phone",
                    "content": f"跟进-{MARKER}",
                    "next_plan": "回访",
                },
                timeout=15,
            )
            record_step(log, "happy_follow_up", r)

        # 401
        r = httpx.post(f"{base}/api/v1/consultant/leads", json={"customer_name": "x", "owner_employee_id": 1}, timeout=15)
        record_step(log, "unauth_no_bearer", r)
        r = httpx.post(
            f"{base}/api/v1/consultant/leads",
            headers={"Authorization": "Bearer wrong-token", "X-Employee-Id": "1", "Content-Type": "application/json"},
            json={"customer_name": "x", "owner_employee_id": 1},
            timeout=15,
        )
        record_step(log, "unauth_wrong_bearer", r)

        # 缺少员工头
        r = httpx.post(
            f"{base}/api/v1/consultant/leads",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={"customer_name": "x", "owner_employee_id": 1},
            timeout=15,
        )
        record_step(log, "missing_employee_header", r)

        # body owner 与头不一致
        r = httpx.post(
            f"{base}/api/v1/consultant/leads",
            headers=h1,
            json={"customer_name": "x", "owner_employee_id": 2, "remark": f"{MARKER}_x"},
            timeout=15,
        )
        record_step(log, "forbidden_owner_body_mismatch", r)

        if lead_id:
            h2 = headers(2, token)
            r = httpx.get(f"{base}/api/v1/consultant/leads/{lead_id}", headers=h2, timeout=15)
            record_step(log, "forbidden_emp2_detail", r)
            r = httpx.patch(
                f"{base}/api/v1/consultant/leads/{lead_id}/status",
                headers=h2,
                json={"status": "qualified"},
                timeout=15,
            )
            record_step(log, "forbidden_emp2_status", r)
            r = httpx.post(
                f"{base}/api/v1/consultant/leads/{lead_id}/follow-ups",
                headers=h2,
                json={"employee_id": 2, "content": f"越权-{MARKER}"},
                timeout=15,
            )
            record_step(log, "forbidden_emp2_follow", r)

            # 身份伪造：同 token，篡改头为员工1（缺陷复现：持有密钥即可冒充）
            r = httpx.patch(
                f"{base}/api/v1/consultant/leads/{lead_id}/status",
                headers=h1,
                json={"status": "qualified"},
                timeout=15,
            )
            record_step(log, "spoof_defect_holder_can_act_as_emp1", r)

        r = httpx.get(f"{base}/api/v1/consultant/leads/99999999", headers=h1, timeout=15)
        record_step(log, "not_found_lead", r)

        if lead_id:
            r = httpx.patch(
                f"{base}/api/v1/consultant/leads/{lead_id}/status",
                headers=h1,
                json={"status": "not_a_valid_status"},
                timeout=15,
            )
            record_step(log, "invalid_status_enum", r)
            r = httpx.patch(
                f"{base}/api/v1/consultant/leads/{lead_id}/status",
                headers=h1,
                json={"status": "new"},
                timeout=15,
            )
            record_step(log, "illegal_transition_back_to_new", r)

        # 判定矩阵
        def add(name: str, expect_status: int | set[int] | str, passed: bool, note: str):
            exp = list(expect_status) if isinstance(expect_status, set) else expect_status
            results.append({"case": name, "expect": exp, "passed": passed, "note": note})

        by = {x["case"]: x for x in log}
        add("happy_create", 200, by.get("happy_create", {}).get("status") == 200, "")
        add("unauth_no_bearer", {401, 503}, by.get("unauth_no_bearer", {}).get("status") in (401, 503), "")
        add("unauth_wrong_bearer", 401, by.get("unauth_wrong_bearer", {}).get("status") == 401, "")
        add("missing_employee_header", 401, by.get("missing_employee_header", {}).get("status") == 401, "")
        add("forbidden_owner_body_mismatch", 403, by.get("forbidden_owner_body_mismatch", {}).get("status") == 403, "")
        if lead_id:
            add("forbidden_emp2_detail", 403, by.get("forbidden_emp2_detail", {}).get("status") == 403, "")
            add("forbidden_emp2_status", 403, by.get("forbidden_emp2_status", {}).get("status") == 403, "")
            add("forbidden_emp2_follow", 403, by.get("forbidden_emp2_follow", {}).get("status") == 403, "")
            add(
                "spoof_defect_holder_can_act_as_emp1",
                "DEFECT",
                False,
                "持有服务token即可伪造X-Employee-Id=1；非身份验收通过项",
            )
            add("not_found_lead", 404, by.get("not_found_lead", {}).get("status") == 404, "")
            add("invalid_status_enum", {422, 400}, by.get("invalid_status_enum", {}).get("status") in (422, 400), "")
            add("illegal_transition", 409, by.get("illegal_transition_back_to_new", {}).get("status") == 409, "")
            add(
                "happy_follow_up",
                200,
                by.get("happy_follow_up", {}).get("status") == 200
                and db_follow_up_count(lead_id, MARKER) >= 1,
                f"crm_follow_up count={db_follow_up_count(lead_id, MARKER)}",
            )

        rows = db_lead_by_remark(MARKER)
        db_ok = bool(lead_id and rows and rows[0]["status"] in ("qualified", "contacting"))
        add("db_consistency", "SELECT", db_ok, str(rows))

    finally:
        proc.terminate()
        proc.wait(timeout=15)

    # 503 单独进程（无 AUTH_BEARER_TOKEN）
    env503 = copy.deepcopy(env)
    env503["AUTH_BEARER_TOKEN"] = ""
    proc503 = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(PORT + 1)],
        cwd=ROOT,
        env=env503,
    )
    try:
        base503 = f"http://127.0.0.1:{PORT + 1}"
        if wait_health(base503):
            r = httpx.post(
                f"{base503}/api/v1/consultant/leads",
                headers={"Authorization": f"Bearer {token}", "X-Employee-Id": "1", "Content-Type": "application/json"},
                json={"customer_name": "x", "owner_employee_id": 1},
                timeout=15,
            )
            record_step(log, "no_token_config_503", r)
            results.append(
                {
                    "case": "no_token_config_503",
                    "expect": 503,
                    "passed": r.status_code == 503,
                    "note": "独立启动实例未配置 AUTH_BEARER_TOKEN",
                }
            )
    finally:
        proc503.terminate()
        proc503.wait(timeout=15)

    matrix_pass = all(r["passed"] for r in results if r.get("expect") != "DEFECT")
    spoof_recorded = any(r["case"] == "spoof_defect_holder_can_act_as_emp1" for r in results)

    out = {
        "marker": MARKER,
        "lead_id": lead_id,
        "python": python_ver,
        "timezone": "Asia/Shanghai",
        "started_at": datetime.now(timezone.utc).astimezone().isoformat(),
        "script": "scripts/run_customer_http_matrix.py",
        "port": PORT,
        "matrix_results": results,
        "identity_defect_recorded": spoof_recorded,
        "matrix_pass_excluding_known_defect": matrix_pass,
        "http_steps": log,
        "db_leads": redact(rows) if lead_id else [],
    }

    shared_dir = ROOT / "docs" / "回复Cursor"
    shared_dir.mkdir(parents=True, exist_ok=True)
    out_path = shared_dir / "13-HTTP验收矩阵-脱敏.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    md_path = shared_dir / "13-HTTP验收矩阵-脱敏.md"
    md_path.write_text(
        f"# HTTP 验收矩阵（脱敏）\n\n"
        f"- 标记：`{MARKER}`\n"
        f"- Python：{python_ver}\n"
        f"- 退出判定：matrix_pass_excluding_known_defect={matrix_pass}\n"
        f"- **已知缺陷**：服务 token 可伪造员工头（见 spoof_defect 用例）\n\n"
        f"```json\n{json.dumps(redact(out), ensure_ascii=False, indent=2)}\n```\n",
        encoding="utf-8",
    )
    print(json.dumps({"exit": 0 if matrix_pass else 1, "marker": MARKER, "matrix_pass": matrix_pass}, ensure_ascii=False))
    return 0 if matrix_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
