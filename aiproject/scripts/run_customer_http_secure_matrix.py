"""app.main 默认 blocked：consultant 各写读路由在身份未就绪时 503；health 200。"""
from __future__ import annotations

import copy
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
RUN_ID = uuid.uuid4().hex[:12]

REQUIRED_CASES = (
    "health_db",
    "main_rejects_insecure_mode",
    "consultant_create_503",
    "consultant_list_503",
    "consultant_detail_503",
    "consultant_patch_lead_503",
    "consultant_status_503",
    "consultant_follow_503",
    "consultant_no_bearer_503",
    "empty_token_still_503",
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


def wait_health(base: str, proc: subprocess.Popen) -> bool:
    for _ in range(40):
        if proc.poll() is not None:
            return False
        try:
            if httpx.get(f"{base}/health/db", timeout=2).status_code == 200:
                return True
        except Exception:
            time.sleep(0.25)
    return False


def auth_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "X-Employee-Id": "1",
        "Content-Type": "application/json",
    }


def main() -> int:
    started_at = datetime.now(timezone.utc).astimezone().isoformat()
    load_env_file()
    os.chdir(ROOT)
    token = os.environ.get("AUTH_BEARER_TOKEN", "")
    if not token:
        print("BLOCKER: AUTH_BEARER_TOKEN 未配置")
        return 2

    results: dict[str, dict] = {}
    port = pick_port()
    env = os.environ.copy()
    env["EMPLOYEE_IDENTITY_MODE"] = "blocked"

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=ROOT,
        env=env,
    )
    base = f"http://127.0.0.1:{port}"
    try:
        if not wait_health(base, proc):
            for c in REQUIRED_CASES:
                if c not in results:
                    results[c] = {"outcome": "FAIL", "reason": "server not ready", "port": port}
        else:
            h = auth_headers(token)
            results["health_db"] = {
                "expected": 200,
                "actual": httpx.get(f"{base}/health/db", timeout=5).status_code,
                "outcome": "PASS" if httpx.get(f"{base}/health/db", timeout=5).status_code == 200 else "FAIL",
            }
            # fix double request - use single
            r0 = httpx.get(f"{base}/health/db", timeout=5)
            results["health_db"] = {
                "expected": 200,
                "actual": r0.status_code,
                "outcome": "PASS" if r0.status_code == 200 else "FAIL",
            }

            def expect503(name: str, resp: httpx.Response) -> None:
                results[name] = {
                    "expected": 503,
                    "actual": resp.status_code,
                    "outcome": "PASS" if resp.status_code == 503 else "FAIL",
                }

            expect503(
                "consultant_create_503",
                httpx.post(f"{base}/api/v1/consultant/leads", headers=h, json={"customer_name": "x", "owner_employee_id": 1}, timeout=10),
            )
            expect503(
                "consultant_list_503",
                httpx.get(f"{base}/api/v1/consultant/leads", headers=h, timeout=10),
            )
            expect503(
                "consultant_detail_503",
                httpx.get(f"{base}/api/v1/consultant/leads/1", headers=h, timeout=10),
            )
            expect503(
                "consultant_patch_lead_503",
                httpx.patch(
                    f"{base}/api/v1/consultant/leads/1",
                    headers=h,
                    json={"contact_info": "13800001111", "intended_country": "德国"},
                    timeout=10,
                ),
            )
            expect503(
                "consultant_status_503",
                httpx.patch(f"{base}/api/v1/consultant/leads/1/status", headers=h, json={"status": "contacting"}, timeout=10),
            )
            expect503(
                "consultant_follow_503",
                httpx.post(f"{base}/api/v1/consultant/leads/1/follow-ups", headers=h, json={"employee_id": 1, "content": "x"}, timeout=10),
            )
            r_nb = httpx.post(f"{base}/api/v1/consultant/leads", json={"customer_name": "x", "owner_employee_id": 1}, timeout=10)
            results["consultant_no_bearer_503"] = {
                "expected": 503,
                "actual": r_nb.status_code,
                "outcome": "PASS" if r_nb.status_code == 503 else "FAIL",
            }
    finally:
        if proc.poll() is None:
            proc.terminate()
            proc.wait(timeout=15)

    # 反向：main 不得接受 insecure 模式
    bad_port = pick_port()
    bad_env = copy.deepcopy(env)
    bad_env["EMPLOYEE_IDENTITY_MODE"] = "insecure_header_repro"
    bad_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(bad_port)],
        cwd=ROOT,
        env=bad_env,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )
    stderr_snip = ""
    try:
        _stdout, stderr_bytes = bad_proc.communicate(timeout=8)
        stderr_snip = (stderr_bytes or b"").decode("utf-8", errors="replace")[-800:]
    except subprocess.TimeoutExpired:
        bad_proc.kill()
        bad_proc.communicate(timeout=5)
        results["main_rejects_insecure_mode"] = {"outcome": "FAIL", "reason": "timeout still running"}
    else:
        port_open = False
        try:
            r_bad = httpx.get(f"http://127.0.0.1:{bad_port}/health/db", timeout=1)
            port_open = r_bad.status_code == 200
        except Exception:
            port_open = False
        reason_ok = "insecure_header_repro" in stderr_snip and "tests.repro.asgi_app" in stderr_snip
        exit_ok = bad_proc.returncode not in (0, None)
        if exit_ok and reason_ok and not port_open:
            results["main_rejects_insecure_mode"] = {
                "outcome": "PASS",
                "exit_code": bad_proc.returncode,
                "stderr_tail_redacted": stderr_snip[-400:],
            }
        else:
            results["main_rejects_insecure_mode"] = {
                "outcome": "FAIL",
                "exit_code": bad_proc.returncode,
                "port_health_200": port_open,
                "reason_matched": reason_ok,
            }

    env503 = copy.deepcopy(env)
    env503["AUTH_BEARER_TOKEN"] = ""
    port2 = pick_port()
    proc2 = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port2)],
        cwd=ROOT,
        env=env503,
    )
    try:
        if wait_health(f"http://127.0.0.1:{port2}", proc2):
            r = httpx.post(
                f"http://127.0.0.1:{port2}/api/v1/consultant/leads",
                headers=auth_headers(token),
                json={"customer_name": "x", "owner_employee_id": 1},
                timeout=10,
            )
            results["empty_token_still_503"] = {
                "expected": 503,
                "actual": r.status_code,
                "outcome": "PASS" if r.status_code == 503 else "FAIL",
                "note": "blocked 下非 token 专属分支",
            }
        else:
            results["empty_token_still_503"] = {"outcome": "FAIL", "reason": "instance not ready"}
    finally:
        if proc2.poll() is None:
            proc2.terminate()
            proc2.wait(timeout=15)

    for c in REQUIRED_CASES:
        if c not in results:
            results[c] = {"outcome": "FAIL", "reason": "missing"}

    finished_at = datetime.now(timezone.utc).astimezone().isoformat()
    all_pass = all(results[c].get("outcome") == "PASS" for c in REQUIRED_CASES)
    out = {
        "run_id": RUN_ID,
        "suite": "secure_blocked_identity",
        "app": "app.main:app",
        "python": sys.version.split()[0],
        "started_at": started_at,
        "finished_at": finished_at,
        "expected_case_set": list(REQUIRED_CASES),
        "results": results,
        "process_exit_code": 0 if all_pass else 1,
    }
    runs_dir = ROOT / "docs" / "回复Cursor" / "runs"
    runs_dir.mkdir(parents=True, exist_ok=True)
    out_path = runs_dir / f"16-secure-{RUN_ID}.md"
    latest = ROOT / "docs" / "回复Cursor" / "16-HTTP安全矩阵-blocked.md"
    body_md = (
        f"# HTTP 安全矩阵（blocked）\n\nrun_id=`{RUN_ID}`\n\n```json\n{json.dumps(out, ensure_ascii=False, indent=2)}\n```\n"
    )
    out_path.write_text(body_md, encoding="utf-8")
    latest.write_text(body_md, encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False))
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
