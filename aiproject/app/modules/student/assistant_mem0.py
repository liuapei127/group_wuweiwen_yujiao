"""Per-account mem0 memory for the student assistant.

Uses Mem0 Platform when ``MEM0_API_KEY`` is set; otherwise a local mem0-shaped
store in ``stu_mem0_memory`` so every account still has durable memory without
shipping full chat history on each request.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.shared.utils.time_util import now_naive

from .assistant_safety import high_risk_hits
from .models import StuMem0Memory

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[\w\u4e00-\u9fff]{2,}")


def user_key(student_id: int) -> str:
    return f"stu_{student_id}"


def search_memories(db: Session, *, student_id: int, query: str, limit: int = 5) -> list[str]:
    uid = user_key(student_id)
    remote = _platform_search(uid, query, limit)
    local = _local_search(db, uid, query, limit)
    if remote is not None:
        # Keep local durable name facts even when platform is configured.
        merged = list(remote)
        for item in local:
            if item not in merged:
                merged.append(item)
        return merged[:limit]
    return local


def remember_turn(
    db: Session,
    *,
    student_id: int,
    user_text: str,
    assistant_text: str,
    conversation_id: str,
) -> None:
    uid = user_key(student_id)
    messages = [
        {"role": "user", "content": (user_text or "")[:1500]},
        {"role": "assistant", "content": (assistant_text or "")[:1500]},
    ]
    if _platform_add(uid, messages, conversation_id):
        return
    fact = _compact_fact(user_text, assistant_text)
    if fact:
        _local_add(db, uid, fact, {"conversation_id": conversation_id})


def memory_preface(memories: list[str]) -> str:
    clean = [m.strip() for m in memories if m and m.strip()]
    if not clean:
        return ""
    lines = "\n".join(f"- {item}" for item in clean[:5])
    # Prefix must not look like leave/feedback menus (those scan the last assistant turn).
    return "【长期记忆】办理时请参考，这不是选项菜单：\n" + lines


def _platform_client():
    key = get_settings().mem0_api_key.get_secret_value().strip()
    if not key:
        return None
    try:
        from mem0 import MemoryClient  # type: ignore
    except Exception:
        logger.warning("MEM0_API_KEY set but mem0 package unavailable; using local memory")
        return None
    return MemoryClient(api_key=key)


def _platform_add(user_id: str, messages: list[dict], run_id: str) -> bool:
    client = _platform_client()
    if client is None:
        return False
    try:
        client.add(messages, user_id=user_id, run_id=run_id, metadata={"source": "student_assistant"})
        return True
    except Exception:
        logger.exception("mem0 platform add failed; falling back to local")
        return False


def _platform_search(user_id: str, query: str, limit: int) -> list[str] | None:
    client = _platform_client()
    if client is None:
        return None
    try:
        result = client.search(query or "学生近况", filters={"user_id": user_id}, top_k=limit)
        rows = result.get("results") if isinstance(result, dict) else result
        out: list[str] = []
        for row in rows or []:
            if isinstance(row, dict):
                text_value = row.get("memory") or row.get("text") or ""
            else:
                text_value = str(row)
            if text_value:
                out.append(str(text_value).strip())
        return out
    except Exception:
        logger.exception("mem0 platform search failed; falling back to local")
        return None


def _local_add(db: Session, user_id: str, memory: str, metadata: dict[str, Any] | None = None) -> None:
    now = now_naive()
    db.add(
        StuMem0Memory(
            user_id=user_id,
            memory=memory[:2000],
            metadata_json=json.dumps(metadata or {}, ensure_ascii=False),
            create_time=now,
            update_time=now,
        )
    )
    db.commit()


def _local_search(db: Session, user_id: str, query: str, limit: int) -> list[str]:
    rows = db.execute(
        select(StuMem0Memory.memory)
        .where(StuMem0Memory.user_id == user_id)
        .order_by(StuMem0Memory.update_time.desc())
        .limit(80)
    ).mappings().all()
    tokens = set(_TOKEN.findall((query or "").lower()))
    # Single-char cues still matter for Chinese short follow-ups.
    for cue in ("假", "病", "事", "进度", "投诉", "考试"):
        if cue in (query or ""):
            tokens.add(cue)
    identity_ask = any(k in (query or "") for k in ("我是谁", "我叫什么", "记得我", "我的名字"))
    if identity_ask:
        tokens.update({"姓名", "名字", "学生姓名"})
    scored: list[tuple[int, str]] = []
    recent: list[str] = []
    for row in rows:
        memory = (row["memory"] or "").strip()
        if not memory:
            continue
        recent.append(memory)
        hay = memory.lower()
        score = sum(1 for tok in tokens if tok in hay) if tokens else 1
        if memory.startswith("学生姓名：") or "学生姓名：" in memory:
            score += 5 if identity_ask else 2
        if score > 0 or not tokens or identity_ask:
            scored.append((score, memory))
    scored.sort(key=lambda item: item[0], reverse=True)
    ordered = [memory for _, memory in scored] if scored else recent
    seen: set[str] = set()
    out: list[str] = []
    for memory in ordered:
        if memory in seen:
            continue
        seen.add(memory)
        out.append(memory)
        if len(out) >= limit:
            break
    return out


_NAME_STOPWORDS = {
    "谁",
    "什么",
    "什么吗",
    "啥",
    "啥吗",
    "哪个",
    "哪个吗",
    "学生",
    "同学",
    "名字",
    "姓名",
}


def _name_fact_from_user(user: str) -> str:
    text = user or ""
    if re.search(r"(?:我叫|叫我|我的名字是)\s*什么|叫什么吗|记得我叫什么|我是谁", text):
        return ""
    hit = re.search(r"(?:我叫|我的名字是|叫我)\s*([A-Za-z\u4e00-\u9fff·]{2,20})", text)
    if not hit:
        return ""
    name = hit.group(1).strip(" ，,。的吗呢啊呀")
    if not name or name in _NAME_STOPWORDS or name.startswith(("什么", "啥", "谁", "哪")):
        return ""
    return f"学生姓名：{name}"


def _compact_fact(user_text: str, assistant_text: str) -> str:
    user = (user_text or "").strip()
    assistant = (assistant_text or "").strip()
    if not user:
        return ""
    # Crisis disclosures stay in the alert tables: never in long-term memory.
    if high_risk_hits(user) or high_risk_hits(assistant):
        return ""
    # Never store failed fallback / internal dumps as memory.
    if any(
        bad in assistant
        for bad in (
            "还没对上要办的事",
            "还没完全对上",
            "我记得你之前提过",
            "助手答复要点",
            "【长期记忆】",
        )
    ):
        return _name_fact_from_user(user)
    name_fact = _name_fact_from_user(user)
    if name_fact:
        return name_fact
    # Prefer durable business facts over chit-chat.
    markers = ("请假", "病假", "事假", "投诉", "进度", "考试", "截止", "德国", "新加坡", "想家", "焦虑", "宿舍")
    if not any(m in user or m in assistant for m in markers):
        if len(user) < 8:
            return ""
    summary = f"学生说：{user[:180]}"
    if assistant and "交上" in assistant:
        summary += f"；办理结果：{assistant[:120]}"
    elif assistant and len(assistant) < 80:
        summary += f"；助手：{assistant[:80]}"
    return summary
