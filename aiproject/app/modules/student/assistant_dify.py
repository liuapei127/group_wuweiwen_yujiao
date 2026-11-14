"""Optional Dify Chatflow shell for the student assistant.

Business leave / feedback / progress / psych stay in ``assistant_chat``.
Dify only forwards the spoken turn when ``STU_DIFY_API_KEY`` is configured.
"""

from __future__ import annotations

import json
from secrets import token_hex

import httpx

from app.core.config import get_settings
from app.core.exceptions import BusinessError


async def ask_dify(
    *,
    query: str,
    access_token: str,
    history: list[dict] | None = None,
    user_key: str,
) -> dict:
    settings = get_settings()
    key = settings.stu_dify_api_key.get_secret_value().strip()
    if not key:
        raise BusinessError(503, "学生助手 Dify 暂未配置")

    payload = {
        "inputs": {
            "student_access_token": access_token,
            "history_json": json.dumps(history or [], ensure_ascii=False),
        },
        "query": query,
        "user": user_key or f"student_{token_hex(8)}",
        "response_mode": "blocking",
    }
    try:
        async with httpx.AsyncClient(
            trust_env=False, timeout=httpx.Timeout(settings.dify_timeout_seconds, connect=5)
        ) as client:
            response = await client.post(
                settings.dify_api_url.rstrip("/") + "/chat-messages",
                headers={"Authorization": "Bearer " + key},
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise BusinessError(502, "学生助手暂不可用，请稍后重试") from exc

    answer = result.get("answer") if isinstance(result, dict) else None
    if not isinstance(answer, str) or not answer.strip():
        raise BusinessError(502, "学生助手未返回有效答复")
    text = answer.strip()
    return {
        "reply": text,
        "answer": text,
        "intent": "dify",
        "form": None,
        "data": {"source": "dify"},
    }
