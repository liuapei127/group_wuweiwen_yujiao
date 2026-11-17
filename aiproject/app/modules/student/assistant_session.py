"""Server-owned student assistant sessions: short DB turns + mem0 long-term memory."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from app.core.exceptions import BusinessError

from . import assistant_chat, assistant_dify, assistant_mem0, assistant_store
from .idempotency import replay_cache

logger = logging.getLogger(__name__)


def create_conversation(db: Session, student_id: int, title: str = "新对话") -> dict:
    return assistant_store.create_conversation(db, student_id, title=title)


def list_conversations(db: Session, student_id: int) -> list[dict]:
    return assistant_store.list_conversations(db, student_id)


def conversation_detail(db: Session, student_id: int, conversation_id: str) -> dict:
    row = assistant_store.get_conversation(db, student_id, conversation_id)
    if row is None:
        raise BusinessError(404, "对话不存在")
    messages = assistant_store.list_messages(db, conversation_id)
    return {
        **row,
        "messages": [
            {"id": m["id"], "role": m["role"], "content": m["content"], "create_time": m["create_time"]}
            for m in messages
        ],
    }


async def run_turn(
    db: Session,
    *,
    student_id: int,
    query: str,
    conversation_id: str | None,
    access_token: str | None,
    use_dify: bool,
    mock_country=None,
    on_text=None,
) -> dict:
    text = (query or "").strip()
    if not text:
        raise BusinessError(422, "请先输入要办的事")

    if conversation_id:
        owned = assistant_store.get_conversation(db, student_id, conversation_id)
        if owned is None:
            raise BusinessError(404, "对话不存在")
        cid = conversation_id
    else:
        cid = assistant_store.create_conversation(db, student_id, title=_title_from(text))["id"]

    # Short-term only: last few turns from this conversation — never full account history.
    history = assistant_store.recent_turns(db, cid, limit=8)
    memories = assistant_mem0.search_memories(db, student_id=student_id, query=text, limit=5)
    # Keep the user query clean for intent routing; inject memories as side context only.
    history_with_memory = history
    preface = assistant_mem0.memory_preface(memories)
    if preface:
        history_with_memory = [
            {"role": "assistant", "content": preface},
            *history,
        ]

    if use_dify and access_token:
        try:
            result = await assistant_dify.ask_dify(
                query=text,
                access_token=access_token,
                history=history_with_memory,
                user_key=assistant_mem0.user_key(student_id),
                **({"on_text": on_text} if on_text else {}),
            )
        except BusinessError as exc:
            # Dify down / misconfigured → keep student flows working on local brain.
            logger.warning("stu dify failed, local fallback: %s", exc)
            if on_text:
                on_text("")
            cache = replay_cache()
            # Dify forwards the query and history. Its callback does not carry mock_country.
            key = cache.key(student_id, text, history_with_memory)

            def local_fallback() -> dict:
                result, _ = cache.remember(
                    key,
                    lambda: assistant_chat.handle_chat(
                        db,
                        student_id=student_id,
                        message=text,
                        history=history_with_memory,
                        mock_country=mock_country,
                        memory_notes=memories,
                        **({"on_text": on_text} if on_text else {}),
                    ),
                )
                return result

            result = await run_in_threadpool(local_fallback)
            result = dict(result)
            result.setdefault("data", {})
            if isinstance(result.get("data"), dict):
                result["data"] = {**result["data"], "source": "local_fallback"}
    else:
        result = await run_in_threadpool(
            assistant_chat.handle_chat, db,
            student_id=student_id,
            message=text,
            history=history_with_memory,
            mock_country=mock_country,
            memory_notes=memories,
            **({"on_text": on_text} if on_text else {}),
        )

    answer = (result.get("answer") or result.get("reply") or "").strip()
    assistant_store.append_turn(
        db,
        student_id=student_id,
        conversation_id=cid,
        user_text=text,
        assistant_text=answer,
        title_hint=_title_from(text),
    )
    try:
        assistant_mem0.remember_turn(
            db,
            student_id=student_id,
            user_text=text,
            assistant_text=answer,
            conversation_id=cid,
        )
    except Exception:
        db.rollback()
        logger.exception("Student assistant memory could not be saved")
    payload = dict(result)
    payload["conversation_id"] = cid
    payload["answer"] = answer
    payload["reply"] = answer
    payload["memories_used"] = memories
    return payload


def _title_from(text: str) -> str:
    clean = " ".join((text or "").strip().split())
    return clean[:28] or "新对话"
