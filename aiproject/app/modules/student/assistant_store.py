"""Persisted student-assistant conversations (short-term turns only).

Schema lives in ``app.modules.student.models`` and is applied by
``migrations/pending/014_student_assistant.sql``; nothing here issues DDL.
"""

from __future__ import annotations

from secrets import token_hex
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.shared.utils.time_util import now_naive

from .models import StudentAssistantConversation, StudentAssistantMessage

MAX_TURN_CHARS = 8000


def _conversation_dict(row: StudentAssistantConversation) -> dict[str, Any]:
    return {
        "id": row.id,
        "title": row.title,
        "create_time": row.create_time,
        "update_time": row.update_time,
    }


def _message_dict(row: StudentAssistantMessage) -> dict[str, Any]:
    return {
        "id": row.id,
        "role": row.role,
        "content": row.content,
        "presentation": row.presentation_json,
        "create_time": row.create_time,
    }


def create_conversation(db: Session, student_id: int, title: str = "新对话") -> dict[str, Any]:
    now = now_naive()
    row = StudentAssistantConversation(
        id=token_hex(16),
        student_id=student_id,
        title=(title or "新对话")[:128],
        create_time=now,
        update_time=now,
    )
    db.add(row)
    db.commit()
    return _conversation_dict(row)


def list_conversations(db: Session, student_id: int, limit: int = 30) -> list[dict[str, Any]]:
    rows = db.scalars(
        select(StudentAssistantConversation)
        .where(StudentAssistantConversation.student_id == student_id)
        .order_by(StudentAssistantConversation.update_time.desc())
        .limit(limit)
    ).all()
    return [_conversation_dict(row) for row in rows]


def get_conversation(db: Session, student_id: int, conversation_id: str) -> dict[str, Any] | None:
    row = db.scalar(
        select(StudentAssistantConversation).where(
            StudentAssistantConversation.id == conversation_id,
            StudentAssistantConversation.student_id == student_id,
        )
    )
    return _conversation_dict(row) if row else None


def list_messages(db: Session, conversation_id: str, limit: int = 100) -> list[dict[str, Any]]:
    """Newest ``limit`` messages, returned oldest first so prompts read naturally."""
    rows = db.scalars(
        select(StudentAssistantMessage)
        .where(StudentAssistantMessage.conversation_id == conversation_id)
        .order_by(StudentAssistantMessage.id.desc())
        .limit(limit)
    ).all()
    return [_message_dict(row) for row in reversed(rows)]


def recent_turns(db: Session, conversation_id: str, limit: int = 8) -> list[dict[str, str]]:
    rows = db.scalars(
        select(StudentAssistantMessage)
        .where(
            StudentAssistantMessage.conversation_id == conversation_id,
            StudentAssistantMessage.role.in_(("user", "assistant")),
        )
        .order_by(StudentAssistantMessage.id.desc())
        .limit(limit)
    ).all()
    return [
        {"role": row.role, "content": row.content}
        for row in reversed(rows)
    ]


def append_turn(
    db: Session,
    *,
    student_id: int,
    conversation_id: str,
    user_text: str,
    assistant_text: str,
    title_hint: str | None = None,
    presentation: dict | None = None,
) -> None:
    owned = db.scalar(
        select(StudentAssistantConversation).where(
            StudentAssistantConversation.id == conversation_id,
            StudentAssistantConversation.student_id == student_id,
        )
    )
    if owned is None:
        raise ValueError("conversation missing")
    now = now_naive()
    db.add_all(
        [
            StudentAssistantMessage(
                conversation_id=conversation_id,
                role="user",
                content=(user_text or "")[:MAX_TURN_CHARS],
                create_time=now,
            ),
            StudentAssistantMessage(
                conversation_id=conversation_id,
                role="assistant",
                content=(assistant_text or "")[:MAX_TURN_CHARS],
                presentation_json=presentation,
                create_time=now,
            ),
        ]
    )
    if owned.title in {"", "新对话"} and title_hint:
        owned.title = title_hint.strip()[:40] or owned.title
    owned.update_time = now
    db.commit()
