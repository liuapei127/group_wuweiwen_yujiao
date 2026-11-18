"""Optional Dify Chatflow shell for the student assistant.

Business leave / feedback / progress / psych stay in ``assistant_chat``.
Dify only forwards the spoken turn when ``STU_DIFY_API_KEY`` is configured.
"""

from __future__ import annotations

import asyncio
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


async def understand(*, query, history, context, task, memories, user_key, country="", stream_plan=False,
                     overall_timeout=None):
    """Read-only model boundary: no bearer token or business callback is exposed to Dify."""
    from .schemas import AssistantUnderstanding
    from pydantic import ValidationError
    settings = get_settings()
    key = settings.stu_dify_api_key.get_secret_value().strip()
    if not key:
        raise BusinessError(503, "学生助手 Dify 暂未配置")
    inputs = {"context_json": json.dumps(context, ensure_ascii=False, default=str),
        "history_json": json.dumps(history, ensure_ascii=False),
        "task_json": json.dumps(task, ensure_ascii=False, default=str),
        "memories_json": json.dumps(memories, ensure_ascii=False), "country": country}
    if stream_plan:
        # The planning branch returns before a complete companion/knowledge reply
        # is generated. The checked visible branch is requested only afterwards.
        inputs["response_stage"] = "plan"
    payload = {"inputs": inputs,
        "query": query, "user": user_key, "response_mode": "blocking"}
    try:
        async with asyncio.timeout(overall_timeout):
            async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(settings.dify_timeout_seconds, connect=5)) as client:
                response = await client.post(settings.dify_api_url.rstrip("/") + "/chat-messages",
                    headers={"Authorization": "Bearer " + key}, json=payload)
                response.raise_for_status()
                answer = response.json().get("answer", "").strip()
                if answer.startswith("```"):
                    answer = answer.split("\n", 1)[1].rsplit("```", 1)[0].strip()
                return AssistantUnderstanding.model_validate_json(answer)
    except (httpx.HTTPError, ValueError, AttributeError, ValidationError, TimeoutError) as exc:
        raise BusinessError(502, "学生助手理解服务暂不可用") from exc


async def stream_reply(*, query, context, history, memories, user_key, country,
                       reviewed_reply, kind, on_text, first_content_timeout=None, overall_timeout=None,
                       safety_context=None, initial_prefix="", reply_evidence=None):
    """A separate read-only generation phase in the same application.

    The Answer node points directly at its LLM so Dify forwards real upstream
    deltas. No student bearer, task confirmation or executable action is sent.
    """
    from .assistant_reply_stream import ReplyGate, StudentReplyInterrupted
    gate = ReplyGate(kind=kind, reviewed_reply=reviewed_reply, query=query, history=history, on_text=on_text,
                     safety_context=safety_context, initial_prefix=initial_prefix, reply_evidence=reply_evidence)
    model_context=context
    model_memories=memories
    if kind=="student_fact" and reply_evidence:
        model_context={"profile":reply_evidence.get("fields",{}),"notes":"只包含本轮所需资料；称呼偏好不修改正式姓名"}
        model_memories=reply_evidence.get("self_reports",[])
    elif kind=="grounded_knowledge":
        model_context={"profile":{"abroad_country":country},"notes":"资料适用国家不是实时定位"}
        model_memories=[]
    settings = get_settings()
    key = settings.stu_dify_api_key.get_secret_value().strip()
    if not key:
        if initial_prefix:
            raise StudentReplyInterrupted(safe_partial=gate.visible, reason_code="reply_not_configured")
        raise BusinessError(503, "学生助手 Dify 暂未配置")
    payload = {
        "inputs": {
            "response_stage": "reply", "country": country or "",
            "reply_context_json": json.dumps({
                "kind": kind, "reviewed_reply": reviewed_reply,
                "student_context": model_context, "recent_user_context": history,
                "self_reported_memories": model_memories,
                "reply_evidence": reply_evidence,
                "safety_context": safety_context or {}, "initial_prefix": initial_prefix,
                "response_instructions": {
                    "continue_after_prefix": bool(initial_prefix),
                    "context_sources": "official records, this owned conversation, and student self-reports are separate",
                    "no_external_action_claims": True,
                    "no_generated_contact_details": True,
                },
            }, ensure_ascii=False, default=str),
        },
        "query": query, "user": user_key, "response_mode": "streaming",
    }
    budgets = {name: value for name, value in {
        "first_content_timeout": first_content_timeout, "overall_timeout": overall_timeout,
    }.items() if value is not None}
    try:
        result = await chat_messages(settings.dify_api_url, key, settings.dify_timeout_seconds, payload, gate.accept, **budgets)
        return gate.finish(result.get("answer", ""))
    except BusinessError as exc:
        raise StudentReplyInterrupted(safe_partial=gate.visible, reason_code="reply_rejected") from exc
    except TimeoutError as exc:
        raise StudentReplyInterrupted(safe_partial=gate.visible, reason_code="reply_timeout") from exc
    except httpx.HTTPError as exc:
        raise StudentReplyInterrupted(safe_partial=gate.visible, reason_code="reply_transport_error") from exc
    except (ValueError, AttributeError) as exc:
        raise StudentReplyInterrupted(safe_partial=gate.visible, reason_code="reply_invalid_response") from exc
