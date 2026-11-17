"""Optional Dify Chatflow shell for the student assistant.

Business leave / feedback / progress / psych stay in ``assistant_chat``.
Dify only forwards the spoken turn when ``STU_DIFY_API_KEY`` is configured.
"""

from __future__ import annotations

import json
from secrets import token_hex

import httpx

from app.ai.dify_stream import chat_messages
from app.core.config import get_settings
from app.core.exceptions import BusinessError

from .assistant_speak import model_text, visible_sentences


async def ask_dify(
    *,
    query: str,
    access_token: str,
    history: list[dict] | None = None,
    user_key: str,
    on_text=None,
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
        if on_text:
            result = await chat_messages(
                settings.dify_api_url, key, settings.dify_timeout_seconds, payload,
                lambda text: _visible_answer(text, on_text),
            )
        else:
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
    text = model_text(answer)
    if not text:
        raise BusinessError(502, "学生助手未返回有效答复")
    if _looks_like_flow_failure(text):
        raise BusinessError(502, "学生助手暂不可用，请稍后重试")
    return {
        "reply": text,
        "answer": text,
        "intent": "dify",
        "form": None,
        "data": {"source": "dify"},
    }


_FLOW_FAILURE_MARKERS = (
    "Run failed",
    "Request failed with status code",
    "Traceback (most recent call last)",
    "暂时没有得到有效回复",
    "学生助手未返回有效答复",
)


def _looks_like_flow_failure(text: str) -> bool:
    """Dify returns its own runtime errors as the answer; treat them as outages."""
    head = (text or "")[:120]
    return any(marker in head for marker in _FLOW_FAILURE_MARKERS)


def _visible_answer(text, on_text):
    if not _looks_like_flow_failure(text):
        visible = visible_sentences(text)
        if visible:
            on_text(visible)


async def understand(*, query, history, context, task, memories, user_key, country=""):
    """Read-only model boundary: no bearer token or business callback is exposed to Dify."""
    from .schemas import AssistantUnderstanding
    from pydantic import ValidationError
    settings = get_settings()
    key = settings.stu_dify_api_key.get_secret_value().strip()
    if not key:
        raise BusinessError(503, "学生助手 Dify 暂未配置")
    payload = {"inputs": {"context_json": json.dumps(context, ensure_ascii=False, default=str),
        "history_json": json.dumps(history, ensure_ascii=False),
        "task_json": json.dumps(task, ensure_ascii=False, default=str),
        "memories_json": json.dumps(memories, ensure_ascii=False), "country": country},
        "query": query, "user": user_key, "response_mode": "blocking"}
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(settings.dify_timeout_seconds, connect=5)) as client:
            response = await client.post(settings.dify_api_url.rstrip("/") + "/chat-messages",
                headers={"Authorization": "Bearer " + key}, json=payload)
            response.raise_for_status()
            answer = response.json().get("answer", "").strip()
            if answer.startswith("```"):
                answer = answer.split("\n", 1)[1].rsplit("```", 1)[0].strip()
            return AssistantUnderstanding.model_validate_json(answer)
    except (httpx.HTTPError, ValueError, AttributeError, ValidationError) as exc:
        raise BusinessError(502, "学生助手理解服务暂不可用") from exc
