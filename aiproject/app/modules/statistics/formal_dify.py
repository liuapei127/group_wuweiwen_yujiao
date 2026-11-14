"""Client for the RPT employee formal-report workflow."""

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.core.exceptions import BusinessError

from .schemas import FormalReportKind, FormalReportSections


def generate_summary(report_kind: FormalReportKind, report_payload: str) -> FormalReportSections:
    return run_summary_workflow(report_kind, report_payload)


def run_summary_workflow(report_kind: str, report_payload: str) -> FormalReportSections:
    settings = get_settings()
    key = settings.dify_employee_formal_api_key.get_secret_value().strip()
    if not key:
        raise BusinessError(503, "员工正式报告工作流尚未配置")
    try:
        with httpx.Client(
            trust_env=False, follow_redirects=False, timeout=httpx.Timeout(settings.dify_timeout_seconds, connect=5)
        ) as client:
            response = client.post(
                settings.dify_api_url.rstrip("/") + "/workflows/run",
                headers={"Authorization": "Bearer " + key},
                json={
                    "inputs": {"report_kind": report_kind, "report_payload": report_payload},
                    "response_mode": "blocking",
                    "user": "rpt-employee-formal",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException as exc:
        raise BusinessError(504, "员工正式报告工作流响应超时") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise BusinessError(502, "员工正式报告工作流暂不可用") from exc

    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict) or data.get("status") != "succeeded":
        raise BusinessError(502, "员工正式报告工作流未完成")
    outputs = data.get("outputs")
    if not isinstance(outputs, dict) or outputs.get("status") != "ok":
        raise BusinessError(502, "员工正式报告工作流输出未通过校验")
    try:
        return FormalReportSections.model_validate(outputs)
    except ValidationError as exc:
        raise BusinessError(502, "员工正式报告工作流输出格式不正确") from exc
