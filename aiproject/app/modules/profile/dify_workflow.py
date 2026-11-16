import httpx
from pydantic import BaseModel, Field, ValidationError

from app.core.config import get_settings
from app.core.exceptions import BusinessError


class ReviewPreview(BaseModel):
    match_result: str = Field(max_length=80)
    match_reason: str = Field(max_length=8000)
    advisor_advice: str | None = Field(default=None, max_length=8000)


def review_text(raw_content: str) -> ReviewPreview:
    settings = get_settings()
    key = settings.pf_dify_api_key.get_secret_value().strip()
    if not key:
        raise BusinessError(503, "Dify 研判尚未配置")
    try:
        with httpx.Client(trust_env=False, timeout=httpx.Timeout(settings.dify_timeout_seconds, connect=5)) as client:
            response = client.post(
                settings.dify_api_url.rstrip("/") + "/workflows/run",
                headers={"Authorization": "Bearer " + key},
                json={
                    "inputs": {"raw_content": raw_content},
                    "response_mode": "blocking",
                    "user": "pf-advisor",
                },
            )
            response.raise_for_status()
            data = response.json()["data"]
            if data["status"] == "succeeded":
                return ReviewPreview.model_validate(data["outputs"])
    except httpx.TimeoutException as exc:
        raise BusinessError(504, "Dify 研判响应超时") from exc
    except (httpx.HTTPError, ValueError, KeyError, TypeError, ValidationError) as exc:
        raise BusinessError(502, "Dify 研判暂不可用") from exc
    raise BusinessError(502, "Dify 研判未完成")
