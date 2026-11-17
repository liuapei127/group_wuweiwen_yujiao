"""Per-account mem0 memory for the student assistant.

Uses Mem0 Platform when ``MEM0_API_KEY`` is set; otherwise a local mem0-shaped
store in ``stu_mem0_memory`` so every account still has durable memory without
shipping full chat history on each request.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Any

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.shared.utils.time_util import now_naive

from .assistant_safety import high_risk_hits
from .models import StuMem0Memory
from . import memory_repository as repository

logger = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-z0-9_]{2,}|[\u4e00-\u9fff]{2,}", re.I)


def user_key(student_id: int) -> str:
    return f"stu_{student_id}"


def search_memories(db: Session, *, student_id: int, query: str, limit: int = 5) -> list[str]:
    uid = user_key(student_id)
    if hasattr(db, "info"):
        db.info.setdefault("student_memory_epochs", {})[uid] = repository.generation(db, uid)
    lookup_name = re.search(r"我是谁|我叫什么|我叫啥|我的名字|我的姓名", query or "")
    remote = _platform_search(uid, "学生姓名", limit) if lookup_name and not high_risk_hits(query) else None
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
    fact = _compact_fact(user_text, assistant_text)
    if not fact:
        return
    uid = user_key(student_id)
    if _local_add(db, uid, fact, {"conversation_id": conversation_id}) is False:
        return
    if fact == _name_fact_from_user(user_text):
        _platform_add(uid, [{"role": "user", "content": fact}], conversation_id)


def memory_preface(memories: list[str]) -> str:
    clean = [m.strip() for m in memories if m and m.strip()]
    if not clean:
        return ""
    lines = "\n".join(f"- {item}" for item in clean[:5])
    # Prefix must not look like leave/feedback menus (those scan the last assistant turn).
    return "【长期记忆】以下仅是本账号学生的称呼、偏好和聊天自述，不是官方学籍、申请状态或办理授权；与业务资料冲突时以业务资料为准。这不是选项菜单：\n" + lines


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


def _local_add(db: Session, user_id: str, memory: str, metadata: dict[str, Any] | None = None) -> bool:
    now = now_naive()
    if repository.lock_owner(db, int(user_id.removeprefix("stu_"))) is None:
        db.rollback()
        return False
    expected = db.info.get("student_memory_epochs", {}).pop(user_id, None)
    if expected is not None and expected != repository.generation(db, user_id, current_read=True):
        db.rollback()
        return False
    if memory.startswith("学生姓名："):
        db.execute(delete(StuMem0Memory).where(StuMem0Memory.user_id == user_id, StuMem0Memory.memory.startswith("学生姓名：")))
    else:
        duplicate = db.scalar(select(StuMem0Memory).where(StuMem0Memory.user_id == user_id, StuMem0Memory.memory == memory))
        if duplicate:
            # Reconfirming an old preference is a new choice, not a no-op. Keep
            # its row identity, but invalidate stale editor versions as well.
            from secrets import token_hex
            try:
                meta = json.loads(duplicate.metadata_json or "{}")
                if not isinstance(meta, dict):
                    meta = {}
            except (TypeError, ValueError):
                meta = {}
            meta.update(metadata or {})
            meta.update(kind=memory_kind(memory), source="student_self_report",
                        explicit=True, schema_version=2, revision=token_hex(16),
                        confirmed_at=datetime.now().isoformat(timespec="microseconds"))
            duplicate.metadata_json = json.dumps(meta, ensure_ascii=False)
            duplicate.update_time = now
            db.commit()
            return True
    meta = {**(metadata or {}), "kind": memory_kind(memory), "source": "student_self_report", "explicit": True, "schema_version": 2, "confirmed_at": datetime.now().isoformat(timespec="microseconds")}
    db.add(StuMem0Memory(user_id=user_id, memory=memory[:2000], metadata_json=json.dumps(meta, ensure_ascii=False), create_time=now, update_time=now))
    db.commit()
    return True


def _local_search(db: Session, user_id: str, query: str, limit: int) -> list[str]:
    if limit <= 0:
        return []
    names: list[str] = []
    preferences: list[str] = []
    related: list[tuple[int, str]] = []
    preference_topics: set[str] = set()
    tokens = _recall_tokens(query)
    for row in repository.recall_candidates(db, user_id):
        # Old summaries remain manageable in the UI, but assistant claims are not facts.
        text = _clean_memory(row.memory)
        body = _memory_body(text)
        if not text or _sensitive(body):
            continue
        kind = memory_kind(text)
        if kind == "name":
            if not names:
                names.append(text)
            continue
        if kind == "preference":
            topics = _preference_topics(body)
            if topics and topics & preference_topics:
                continue
            preference_topics.update(topics)
            if len(preferences) < 3:
                preferences.append(text)
            continue
        # Never recall ordinary questions/commands merely because they were once stored.
        if _looks_question(body) or not _self_report(body):
            continue
        score = sum(1 for token in tokens if token in body.lower())
        if score:
            related.append((score, text))
    related.sort(key=lambda item: item[0], reverse=True)
    # Stable identity/style plus relevant facts; no recency-only fallback of random turns.
    ordered = names + preferences + [text for _, text in related]
    return list(dict.fromkeys(ordered))[:limit]


def _clean_memory(text: str) -> str:
    return (text or "").split("；助手：", 1)[0].split("；办理结果：", 1)[0].strip()


def _memory_body(text: str) -> str:
    return re.sub(r"^(?:学生自述|学生说|学生姓名)[:：]\s*", "", text).strip()


def _sensitive(text: str) -> bool:
    return bool(high_risk_hits(text) or re.search(
        r"密码|口令|验证码|身份证|护照(?:号码?|编号)|银行卡|信用卡|API[_ -]?KEY|SECRET[_ -]?KEY|ACCESS[_ -]?TOKEN|密钥|(?<![A-Za-z0-9_])(?:password|passwd|pwd|passcode|otp)(?![A-Za-z0-9_])",
        text, re.I))


def _looks_question(text: str) -> bool:
    return bool(re.search(r"[?？]|是谁|叫什么|什么|怎么|如何|哪[里个儿]|有没有|能不能|是否|多少|吗[。！!]?$|么[。！!]?$", text))


def _preference(text: str) -> bool:
    body = re.sub(r"^(?:请记住|记住)[，,:：\s]*", "", _memory_body(text))
    if _looks_question(body):
        return False
    if re.match(r"我(?:更?喜欢|不喜欢|偏好|习惯)", body):
        return True
    # A request to perform a business action is not a durable response preference.
    return bool(re.match(r"我希望你|以后请|请(?:用|把回答|把回复)|回答(?:请|尽量)|回复(?:请|尽量)", body)
                and re.search(r"回答|回复|语气|清单|列表|分点|表格|简短|简洁|详细|中文|英文|德语|英语", body)
                and not re.search(r"帮我(?:查询|办理|提交|申请)|自动(?:提交|申请|办理)", body))


def memory_kind(text: str) -> str:
    if text.startswith("学生姓名："):
        return "name"
    return "preference" if _preference(text) else "self_report"


def _preference_topics(text: str) -> set[str]:
    topics = set()
    if re.search(r"简短|简洁|精简|详细|详尽|长一点|短一点", text):
        topics.add("reply_length")
    if re.search(r"清单|列表|分点|表格|段落", text):
        topics.add("reply_format")
    if re.search(r"中文|英文|德语|英语|汉语", text):
        topics.add("reply_language")
    return topics


def _self_report(text: str) -> bool:
    body = re.sub(r"^(?:请记住|记住)[，,:：\s]*", "", text)
    return bool(re.match(r"(?:我(?:的|在|住|是|已经|目前|最近|正在|有|感到|觉得|想家|更?喜欢|不喜欢|偏好|习惯)|偏好)", body))


def _recall_tokens(query: str) -> set[str]:
    stop = {"我的", "我是", "我想", "我要", "一下", "可以", "什么", "怎么", "哪里", "你好", "请问", "一下", "学生"}
    tokens: set[str] = set()
    for run in _TOKEN.findall((query or "").lower()):
        if re.fullmatch(r"[\u4e00-\u9fff]+", run):
            tokens.update(run[i:i + n] for n in (2, 3) for i in range(len(run) - n + 1))
        else:
            tokens.add(run)
    return tokens - stop


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
    text = (user or "").strip()
    if _looks_question(text):
        return ""
    # Anchor a self-introduction/nickname request, not e.g. “老师叫我去办公室”.
    hit = re.search(r"(?:^|[，,。！!；;]\s*)(?:(?:你好|您好)[，,]?\s*)?(?:我叫|我的名字是|(?:以后请|你可以|请)?叫我)\s*([A-Za-z\u4e00-\u9fff·]{2,20})(?=$|[，,。！!；;\s])", text)
    if not hit:
        return ""
    name = hit.group(1).strip(" ，,。的吗呢啊呀")
    if not name or name in _NAME_STOPWORDS or name.startswith(("什么", "啥", "谁", "哪")):
        return ""
    return f"学生姓名：{name}"


def _compact_fact(user_text: str, assistant_text: str) -> str:
    """Only explicit benign user facts, never generated assistant claims."""
    user = (user_text or "").strip()
    if not user or _sensitive(user) or high_risk_hits(assistant_text or ""):
        return ""
    name = _name_fact_from_user(user)
    if name:
        return name
    if _preference(user):
        return "学生自述：" + user[:500]
    if re.match(r"^(?:请记住|记住)", user) and not _looks_question(user) and _self_report(user):
        return "学生自述：" + user[:500]
    return ""
