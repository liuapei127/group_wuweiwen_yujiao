"""ENT + Dify 本地验收脚本（不依赖控制台 Cookie）。"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "回复Cursor" / "runs" / "ent-dify-acceptance-latest.json"


def run_pytest() -> dict:
    proc = subprocess.run(
        [str(ROOT / ".venv313" / "Scripts" / "python.exe"), "-X", "utf8", "-m", "pytest", "tests", "-q"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return {"exit_code": proc.returncode, "stdout": proc.stdout.strip(), "stderr": proc.stderr.strip()}


def probe_api() -> dict:
    base = "http://127.0.0.1:8000"
    out: dict = {"base": base}
    with httpx.Client(timeout=10.0) as client:
        health = client.get(f"{base}/health")
        out["health_status"] = health.status_code
        out["health"] = health.json()
        r = client.post(
            f"{base}/api/v1/consultant/leads",
            json={"customer_name": "acceptance_probe"},
        )
        out["consultant_post_status"] = r.status_code
        out["consultant_post_body"] = r.text[:300]
    return out


def probe_from_dify_container() -> dict:
    cmd = [
        "docker",
        "exec",
        "dify-api-1",
        "curl",
        "-s",
        "-m",
        "8",
        "http://host.docker.internal:8000/health",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    return {
        "exit_code": proc.returncode,
        "stdout": proc.stdout.strip(),
        "stderr": proc.stderr.strip()[:200],
    }


def evaluate_report(report):
    container=report["api_from_dify_container"]
    try:container_body=json.loads(container["stdout"])
    except (ValueError,TypeError):container_body={}
    checks={
        "pytest":report["pytest"]["exit_code"]==0,
        "host_health_status":report["api_host"].get("health_status")==200,
        "host_health_body":report["api_host"].get("health",{}).get("status")=="ok",
        "business_auth_blocked":report["api_host"].get("consultant_post_status")==503,
        "container_health":container["exit_code"]==0 and container_body.get("status")=="ok",
    }
    return checks


def main() -> int:
    report = {
        "at": datetime.now(timezone.utc).isoformat(),
        "dify_app_id": "ac18cfb8-3f60-406f-99dd-d9cc635dc71f",
        "dify_console": "http://127.0.0.1:8088/app/ac18cfb8-3f60-406f-99dd-d9cc635dc71f/workflow",
        "pytest": run_pytest(),
        "api_host": probe_api(),
        "api_from_dify_container": probe_from_dify_container(),
        "notes": [
            "Dify 工作流含：探活→LLM→代码→分支→HTTP POST/GET→回复",
            "app.main 业务 POST 预期 503（blocked）",
            "Dify 对话跑通后应在回复中看到 503 或 API 响应体，禁止谎称录入成功",
        ],
    }
    report["scope"] = "Basic infrastructure only; does not validate Dify dialogues or writes"
    report["checks"] = evaluate_report(report)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if all(report["checks"].values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
