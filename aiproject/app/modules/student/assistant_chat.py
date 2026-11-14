"""Spoken student assistant wired into unified modules.

Cross-module links:
- leave → student_admin (todo sync for ENT approval)
- complaints → feedback (ticket sync for staff)
- progress / deadlines → student.service
- psych → silent psych tables + teacher notification_log (staff psych-alerts)
- policies / overseas → study_policies + overseas_resources
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any, Literal, Optional

from sqlalchemy import BigInteger, Date, DateTime, String, Text, column, insert, select, table
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.modules.feedback import service as feedback_service
from app.modules.feedback.schemas import StudentComplaintCreate
from app.modules.student import service as student_service
from app.modules.student_admin.repository import StudentAdminRepository
from app.modules.student_admin.schemas import StudentLeaveCreate
from app.modules.student_admin.service import StudentAdminServiceLayer
from app.modules.todo.models import notification_log
from app.modules.visitor.repository import student_destination
from app.shared.utils.time_util import now_naive

from .assistant_intent import route
from .assistant_llm import speak
from .assistant_safety import high_risk_hits
from .assistant_speak import feedback_summary, student_safe

LEAVE_TYPE_LABEL = {"sick": "病假", "personal": "事假", "emergency": "紧急"}
LEAVE_STATUS_SPOKEN = {
    "pending": "还在等审批",
    "approved": "已经通过",
    "rejected": "没有通过",
}
STAGE_LABEL = {
    "document_prep": "材料准备",
    "submitted": "已提交",
    "under_review": "审核中",
    "offer_received": "已录取",
    "visa_processing": "签证办理",
    "enrolled": "已入学",
}
DEADLINE_STATUS_LABEL = {
    "pending": "还没完成",
    "reminded": "已经提醒过",
    "done": "已经完成",
    "missed": "已经错过",
}
_FEEDBACK_CHOICES = (
    ("正式投诉", "complaint", "正式投诉"),
    ("提建议", "suggestion", "建议"),
    ("先咨询", "consult", "咨询"),
)
_TYPE_RE = re.compile(r"(?:请假类型\s*[:：]\s*)?(病假|事假|紧急|sick|personal|emergency)")
_START_RE = re.compile(
    r"开始时间\s*[:：]\s*(\d{4}-\d{2}-\d{2}(?:[T\s]\d{1,2}:\d{2}(?::\d{2})?)?)"
)
_END_RE = re.compile(
    r"结束时间\s*[:：]\s*(\d{4}-\d{2}-\d{2}(?:[T\s]\d{1,2}:\d{2}(?::\d{2})?)?)"
)
_REASON_RE = re.compile(r"事由\s*[:：]\s*(.+)")
_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")
_DATE_RANGE_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2})\s*(?:到|至|~|—|–|-)\s*(\d{4}-\d{2}-\d{2})"
)
_DATE_TIME_RANGE_RE = re.compile(
    r"(\d{4}-\d{2}-\d{2}(?:[T\s]\d{1,2}:\d{2}(?::\d{2})?)?)\s*(?:到|至|~|—|–|-)\s*"
    r"(\d{4}-\d{2}-\d{2}(?:[T\s]\d{1,2}:\d{2}(?::\d{2})?)?)"
)
_CN_RANGE_RE = re.compile(
    r"(\d{1,2})\s*月\s*(\d{1,2})\s*(?:号|日)?\s*(?:到|至|~|—|–|-)\s*"
    r"(?:(\d{1,2})\s*月\s*)?(\d{1,2})\s*(?:号|日)?"
)
_DAY_RANGE_RE = re.compile(
    r"(\d{1,2})\s*号+\s*(?:到|至|~|—|–|-)\s*(\d{1,2})\s*号+"
)
_NAME_RE = re.compile(
    r"(?:我叫|我的名字是|叫我)\s*([A-Za-z\u4e00-\u9fff·]{2,20})"
)
_CLOCK_SPAN_RE = re.compile(
    r"(?:(上午|下午|晚上)\s*)?(?<![\d:])(\d{1,2})\s*点?\s*(?:[:：](\d{2}))?\s*"
    r"[到至\-–—]\s*(?:(上午|下午|晚上)\s*)?(\d{1,2})\s*点?\s*(?:[:：](\d{2}))?"
)
_NATURAL_RANGE_RE = re.compile(r"(今天|明天|后天)\s*(?:到|至|~|—|–|-)\s*(今天|明天|后天)")
_MD_RANGE_RE = re.compile(
    r"(?<!\d)(\d{1,2})\s*[-/]\s*(\d{1,2})\s*(?:到|至|~|—|–|-)\s*"
    r"(\d{1,2})\s*[-/]\s*(\d{1,2})(?!\d)"
)

# Assistant lines that mean "a leave slot is still open" / "the leave was filed".
_LEAVE_PROMPT_CUES = (
    "先选一种",
    "先按病假",
    "先按事假",
    "先按紧急",
    "请再补充",
    "起止日期",
    "请假类型",
    "一口气说完",
    "可以请假",
    "相同时间段",
    "换一组日期",
    "结束时间要晚于",
    "时间格式不对",
)
_LEAVE_SUCCESS_CUES = (
    "已经帮你交上",
    "已经交上",
    "帮你交上",
    "提交成功",
)
_CANCEL_WORDS = ("算了", "取消", "不请了", "不用了", "先不请", "不办了", "退出")
_ACK_WORDS = ("谢谢", "好的", "好", "嗯", "哦", "知道了", "收到", "行", "可以", "没事")
_REASON_STOPWORDS = {
    "谢谢",
    "谢谢你",
    "好的",
    "好",
    "嗯",
    "哦",
    "在吗",
    "你好",
    "您好",
    "可以",
    "行",
    "没事",
    "算了",
    "取消",
    "不请了",
    "不用了",
    "知道了",
    "收到",
    "对的",
    "是的",
    "不是",
}

_psych_alert = table(
    "student_psych_alert",
    column("id", BigInteger),
    column("student_id", BigInteger),
    column("teacher_id", BigInteger),
    column("risk_level", String),
    column("status", String),
    column("trigger_reason", Text),
    column("create_time", DateTime),
    column("update_time", DateTime),
)
_psych_record = table(
    "student_psych_record",
    column("id", BigInteger),
    column("student_id", BigInteger),
    column("interaction_content", Text),
    column("record_date", Date),
    column("create_time", DateTime),
)


def leave_form(student_id: int) -> dict:
    return {
        "title": "请假单",
        "student_id": student_id,
        "fields": [
            {
                "name": "leave_type",
                "label": "请假类型",
                "required": True,
                "options": [
                    {"value": "sick", "label": "病假"},
                    {"value": "personal", "label": "事假"},
                    {"value": "emergency", "label": "紧急"},
                ],
            },
            {
                "name": "start_time",
                "label": "开始时间",
                "required": True,
                "example": "2026-11-13T09:00:00",
            },
            {
                "name": "end_time",
                "label": "结束时间",
                "required": True,
                "example": "2026-11-13T18:00:00",
            },
            {"name": "reason", "label": "事由", "required": True},
        ],
        "submit": {"method": "POST", "path": "/api/v1/student/leaves"},
    }


def handle_chat(
    db: Session,
    *,
    student_id: int,
    message: str,
    history: list | None = None,
    mock_country: Literal["Germany", "Singapore"] | None = None,
    memory_notes: list[str] | None = None,
) -> dict:
    turns = history or []
    memories = _merge_memories(memory_notes, turns)
    place = _place_label(db, student_id, mock_country)
    name = _heard_name(message)
    if name:
        memories = _upsert_name_memory(memories, name)
    if _asks_who_am_i(message):
        return _pack(_identity_reply(message, place, memories, name))
    # Clear self-intro wins over an open leave/feedback slot fill.
    if name and not _looks_like_leave_slot(message):
        return _pack(
            {
                "reply": f"好的，{name}。我记住你了。想请假、查进度、看考试截止或投诉，直接跟我说就行。",
                "intent": "identity",
                "form": None,
                "data": {"name": name, "memories": memories},
            }
        )
    forced, spoken = _follow_choice(message, turns)
    if forced == "leave":
        return _pack(_leave_dialogue(db, student_id, spoken, place, turns))
    if forced == "feedback":
        return _pack(_feedback(db, student_id, spoken, turns, place))
    if _leave_pending(turns) and _is_cancel(message):
        return _pack(
            {
                "reply": "好，这次先不请假了。需要的时候再说「我要请假」，我随时帮你办。",
                "intent": "leave_cancel",
                "form": None,
                "data": None,
            }
        )
    if _feedback_menu_open(turns) and _is_cancel(message):
        return _pack(
            {
                "reply": "好，这次先不记了。以后想投诉、提建议或咨询，随时跟我说。",
                "intent": "feedback_cancel",
                "form": None,
                "data": None,
            }
        )
    if (
        _is_ack(message)
        and _last_assistant(turns)
        and not _leave_pending(turns)
        and not _feedback_menu_open(turns)
    ):
        return _pack(
            {
                "reply": "不客气，有请假、进度、考务或投诉的事随时找我。",
                "intent": "chat",
                "form": None,
                "data": None,
            }
        )
    intent = route(message)["intent"]
    if _picked_feedback(message, turns) or intent == "feedback":
        return _pack(_feedback(db, student_id, message, turns, place))
    if intent == "leave_create" or (
        _leave_pending(turns) and not _psych_pending(turns) and intent != "psych"
    ):
        return _pack(_leave_dialogue(db, student_id, message, place, turns))
    if intent == "leave_query":
        return _pack(_leave_query(db, student_id))
    if intent == "progress":
        return _pack(_progress(db, student_id))
    if intent == "deadline":
        return _pack(_deadline(db, student_id))
    if intent == "psych" or (_psych_pending(turns) and intent == "other"):
        return _pack(_psych(db, student_id, message, turns, place))
    if intent == "ask":
        return _pack(_ask(db, student_id, message, place, turns, memories))
    if _wants_upgrade(message):
        return _pack(_upgrade_reply(message, place, turns))
    return _pack(
        {
            "reply": _chat_reply(message, place, turns, memories),
            "intent": "chat",
            "form": None,
            "data": {"place": place, "memories": memories},
        }
    )


def _pack(payload: dict) -> dict:
    reply = student_safe(payload.get("reply") or "")
    payload["reply"] = reply
    payload["answer"] = reply  # WebsiteAssistant + CS-shaped clients
    return payload


def _place_label(
    db: Session, student_id: int, mock_country: Literal["Germany", "Singapore"] | None
) -> str:
    if mock_country == "Germany":
        return "德国方向"
    if mock_country == "Singapore":
        return "新加坡方向"
    raw = student_destination(db, student_id)
    policies = student_service.student_policies(db, student_id)
    if policies.country == "Germany":
        return "德国方向"
    if policies.country == "Singapore":
        return "新加坡方向"
    return (raw or "").strip() or "还没登记"


def _leave_kind(message: str) -> str:
    text = message or ""
    if "病假" in text or "生病" in text or any(
        k in text for k in ("肚子疼", "肚子痛", "发烧", "感冒", "身体不适")
    ):
        return "病假"
    if "紧急" in text:
        return "紧急"
    if "事假" in text:
        return "事假"
    return ""


def _merge_memories(memory_notes: list[str] | None, history: list | None) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in memory_notes or []:
        text = (item or "").strip()
        if text and text not in seen:
            seen.add(text)
            out.append(text)
    for turn in history or []:
        content = (turn.get("content") or "").strip()
        if not content.startswith("【长期记忆】"):
            continue
        for line in content.splitlines():
            line = line.lstrip("- ").strip()
            if line and "长期记忆" not in line and line not in seen:
                seen.add(line)
                out.append(line)
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


def _looks_like_leave_slot(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if _DAY_RANGE_RE.search(text) or re.search(r"\d{1,2}\s*号", text) or _TYPE_RE.search(text):
        return True
    return any(k in text for k in ("请假", "病假", "事假", "紧急"))


def _heard_name(message: str) -> str:
    text = message or ""
    # Questions like「你还记得我叫什么吗」must never invent a name.
    if re.search(r"(?:我叫|叫我|我的名字是)\s*什么|叫什么吗|记得我叫什么|我是谁", text):
        return ""
    matched = _NAME_RE.search(text)
    if not matched:
        return ""
    name = matched.group(1).strip(" ，,。的吗呢啊呀")
    if not name or name in _NAME_STOPWORDS or name.startswith(("什么", "啥", "谁", "哪")):
        return ""
    return name


def _upsert_name_memory(memories: list[str], name: str) -> list[str]:
    fact = f"学生姓名：{name}"
    cleaned = [m for m in memories if not str(m).startswith("学生姓名：")]
    return [fact, *cleaned]


def _asks_who_am_i(message: str) -> bool:
    text = (message or "").strip()
    if any(k in text for k in ("请假", "进度", "投诉", "建议", "考试", "截止")):
        return False
    return any(
        k in text
        for k in (
            "我是谁",
            "我叫什么",
            "记得我叫什么",
            "记得我的名字",
            "我的名字是什么",
            "我叫啥",
            "你还记得我叫",
            "你还记得我的名字",
        )
    )


def _name_from_memory_list(memories: list[str]) -> str:
    for item in memories:
        text = str(item)
        if text.startswith("学生姓名："):
            name = text.split("：", 1)[-1].strip()
            if name and name not in _NAME_STOPWORDS and not name.startswith(("什么", "啥", "谁")):
                return name
        matched = _NAME_RE.search(text.replace("学生说：", ""))
        if matched:
            name = matched.group(1).strip(" ，,。的吗呢啊呀")
            if name and name not in _NAME_STOPWORDS and not name.startswith(("什么", "啥", "谁")):
                return name
    return ""


def _identity_reply(
    message: str, place: str, memories: list[str], just_told: str = ""
) -> dict:
    name = (just_told or "").strip()
    if not name or name in _NAME_STOPWORDS or name.startswith(("什么", "啥", "谁")):
        name = _name_from_memory_list(memories)
    if name:
        reply = f"你是{name}。我这边按你的留学去向（{place}）继续帮你办请假、进度、考务和投诉就行。"
    else:
        reply = "我这边还没有记下你的名字。你可以先说「我叫某某」，我记住后就能直接叫你。"
    return {
        "reply": reply,
        "intent": "identity",
        "form": None,
        "data": {"name": name or None, "memories": memories},
    }


def _feedback_menu_open(history: list | None) -> bool:
    last = _last_assistant(history or [])
    return "正式投诉" in last and "提建议" in last and "先咨询" in last


def _picked_feedback(message: str, history: list | None = None):
    text = (message or "").strip()
    for label, ticket_type, spoken in _FEEDBACK_CHOICES:
        if text == label or text.startswith(label) or label in text[:8]:
            return ticket_type, spoken
    # Bare 1/2/3 only after the assistant actually offered the menu
    if not _feedback_menu_open(history):
        return None
    if text in {"1", "①"}:
        return "complaint", "正式投诉"
    if text in {"2", "②"}:
        return "suggestion", "建议"
    if text in {"3", "③"}:
        return "consult", "咨询"
    return None


def _care(message: str) -> str:
    return "听起来挺让人烦心的。" if message else "我在听。"


def _feedback_choices() -> str:
    return "你想怎么处理？回 1 正式投诉，回 2 提建议，回 3 先咨询。"


_FEEDBACK_DETAIL_CUE = "说说具体是哪件事"
_FEEDBACK_TRIGGER_WORDS = (
    "我要投诉",
    "我想投诉",
    "我要提建议",
    "我想提建议",
    "我要反馈",
    "我想反馈",
    "投诉",
    "建议",
    "反馈",
    "举报",
)


def _has_substance(text: str, minimum: int = 8) -> bool:
    """「我要投诉」只是开场，不能当成投诉正文直接开单。"""
    value = (text or "").strip()
    for word in _FEEDBACK_TRIGGER_WORDS:
        value = value.replace(word, "")
    value = re.sub(r"[\s，。,.!！?？、~～]+", "", value)
    return len(value) >= minimum


def _feedback_detail_pending(history: list | None) -> Optional[str]:
    """We asked for the details; the next user turn is what to file."""
    last = _last_assistant(history or [])
    if _FEEDBACK_DETAIL_CUE not in last:
        return None
    return "suggestion" if "建议" in last and "投诉" not in last else "complaint"


def _is_feedback_detail_reply(message: str, history: list | None) -> bool:
    if not _feedback_detail_pending(history) or not _has_substance(message, 4):
        return False
    return route(message)["intent"] not in {
        "psych",
        "leave_create",
        "leave_query",
        "progress",
        "deadline",
    }


def _feedback_detail(message: str, history: list) -> str:
    picked = _picked_feedback(message, history)
    if picked and message.strip() in {"1", "2", "3", "①", "②", "③", picked[1], "正式投诉", "提建议", "先咨询"}:
        for turn in reversed(history or []):
            if turn.get("role") == "user":
                content = (turn.get("content") or "").strip()
                if content and _picked_feedback(content) is None and "投诉" not in content[:2]:
                    return content
        return message
    return message


def _choice_index(message: str) -> str:
    text = (message or "").strip()
    if text in {"1", "①", "一"}:
        return "1"
    if text in {"2", "②", "二"}:
        return "2"
    if text in {"3", "③", "三"}:
        return "3"
    return ""


def _last_assistant(history: list) -> str:
    for turn in reversed(history or []):
        if turn.get("role") != "assistant":
            continue
        content = (turn.get("content") or "").strip()
        if content.startswith("【长期记忆】"):
            continue
        return content
    return ""


def _changed_topic(message: str) -> bool:
    intent = route(message)["intent"]
    return intent not in {"other"}


def _psych_pending(history: list | None) -> bool:
    last = _last_assistant(history or [])
    if not last:
        return False
    return any(
        cue in last
        for cue in (
            "陪你聊聊",
            "想家",
            "心里不踏实",
            "最难受",
            "我很担心你",
            "慢慢跟我说说",
            "班主任说一声",
        )
    )


def _leave_success_text(text: str) -> bool:
    return any(cue in (text or "") for cue in _LEAVE_SUCCESS_CUES)


def _leave_prompt_text(text: str) -> bool:
    return any(cue in (text or "") for cue in _LEAVE_PROMPT_CUES)


def _is_cancel(message: str) -> bool:
    text = re.sub(r"[\s，,。.!！~～、]+", "", message or "")
    if not text or len(text) > 8:
        return False
    return any(word in text for word in _CANCEL_WORDS)


def _is_ack(message: str) -> bool:
    text = re.sub(r"[\s，,。.!！~～、]+", "", message or "")
    if not text or len(text) > 6:
        return False
    return any(text.startswith(word) for word in _ACK_WORDS)


def _leave_pending(history: list | None) -> bool:
    """True only while the last assistant turn is an unanswered leave prompt.

    A filed leave ends the slot, so a later「谢谢」or a brand-new request can no
    longer be swallowed by the previous leave dialogue.
    """
    last = _last_assistant(history or [])
    if not last or _leave_success_text(last):
        return False
    return _leave_prompt_text(last)


def _follow_choice(message: str, history: list):
    number = _choice_index(message)
    in_leave = _leave_pending(history)
    in_feedback = _feedback_menu_open(history) or bool(_feedback_detail_pending(history))
    # 「算了」must escape an open slot instead of becoming a leave reason.
    if (in_leave or in_feedback) and _is_cancel(message):
        return None, message
    # Date-only / day-range follow-ups must stay in leave even if router says other.
    if _looks_like_leave_followup(message) and in_leave:
        return "leave", _compose_leave_utterance(message, history)
    if (in_leave or in_feedback) and not number and _changed_topic(message):
        if not _is_feedback_detail_reply(message, history):
            return None, message
    if in_leave:
        kind = {"1": "病假", "2": "事假", "3": "紧急"}.get(number) or _leave_kind(message)
        spoken = _compose_leave_utterance(message, history)
        if kind and number:
            return "leave", f"{kind}。{spoken}"
        return "leave", spoken
    if in_feedback:
        return "feedback", message
    return None, message


def _looks_like_leave_followup(message: str) -> bool:
    text = (message or "").strip()
    if not text:
        return False
    if _DATE_RE.search(text) or _DATE_RANGE_RE.search(text) or _CN_RANGE_RE.search(text):
        return True
    if _DAY_RANGE_RE.search(text):
        return True
    if any(k in text for k in ("明天", "后天", "今天", "号", "事由", "因为")):
        return True
    return False


def _leave_scope(history: list | None) -> list[dict]:
    """Turns belonging to the current leave dialogue, newest last.

    Stops at the assistant prompt that opened the dialogue (or at a filed
    leave), so facts from an earlier leave can never leak into this one.
    """
    scoped: list[dict] = []
    for turn in reversed((history or [])[-12:]):
        content = (turn.get("content") or "").strip()
        if content.startswith("【长期记忆】"):
            continue
        if turn.get("role") == "assistant":
            if not content:
                continue
            # Filed leave, or an unrelated answer, closes the dialogue.
            if _leave_success_text(content) or not _leave_prompt_text(content):
                break
            continue
        if not content:
            continue
        if _looks_like_leave_followup(content) or route(content)["intent"] == "leave_create" or _leave_kind(content):
            scoped.insert(0, turn)
    return scoped[-3:]


def _compose_leave_utterance(message: str, history: list | None) -> str:
    """Merge the current turn with the open leave dialogue so slot-filling can finish."""
    parts: list[str] = []
    current = (message or "").strip()
    if _leave_pending(history):
        for turn in _leave_scope(history):
            content = (turn.get("content") or "").strip()
            if content and content != current:
                parts.append(content)
        # Keep the type the assistant already proposed (先按病假).
        kind = _leave_kind(_last_assistant(history or []))
        if kind and kind not in current and not any(kind in part for part in parts):
            parts.insert(0, kind)
    # A bare「1/2/3」only picks the type; it is not leave content.
    if current and current not in parts and not (_choice_index(current) and parts):
        parts.append(current)
    # 学生改了日期时，旧日期不能再留在合并句子里，否则会按上一轮判重复。
    dated = [index for index, part in enumerate(parts) if _leave_has_span(part)]
    if len(dated) > 1:
        newest = dated[-1]
        parts = [part for index, part in enumerate(parts) if index == newest or index not in dated]
    return "。".join(parts)


def _leave_has_span(text: str) -> bool:
    value = text or ""
    return any(
        pattern.search(value)
        for pattern in (
            _DATE_TIME_RANGE_RE,
            _DATE_RANGE_RE,
            _CN_RANGE_RE,
            _DAY_RANGE_RE,
            _CLOCK_SPAN_RE,
            _NATURAL_RANGE_RE,
            _MD_RANGE_RE,
        )
    )


def _natural_leave(message: str, history: list | None = None) -> Optional[dict]:
    text = (message or "").strip()
    kind = _leave_kind(text) or _leave_kind(_last_assistant(history or []))
    # Stomach ache / 肚子疼 etc. imply sick leave.
    if not kind and any(k in text for k in ("肚子疼", "肚子痛", "发烧", "感冒", "身体不适", "生病", "看病")):
        kind = "病假"
    leave_type = None
    if kind:
        leave_type = {"病假": "sick", "事假": "personal", "紧急": "emergency"}[kind]
    reason = _heard_reason(text)
    if not reason and any(k in text for k in ("肚子疼", "肚子痛", "发烧", "感冒", "身体不适")):
        for cue in ("肚子疼", "肚子痛", "发烧", "感冒", "身体不适"):
            if cue in text:
                reason = cue
                break
    start_time = end_time = None

    filled = parse_filled_form(text)
    if filled:
        return filled

    start_time, end_time = _parse_leave_span(text)
    if not (leave_type and start_time and end_time and reason):
        return None
    return {
        "leave_type": leave_type,
        "start_time": start_time,
        "end_time": end_time,
        "reason": reason[:500],
    }


_WEEKDAY_OFFSET = {"今天": 0, "明天": 1, "后天": 2}


# 「11-01」said on 11-14 means the past 1 November, not next year's: only roll
# a month/day into the future when that future date is reasonably close.
MAX_LOOKAHEAD_DAYS = 180


def _future_month_day(base: date, month: int, day: int) -> Optional[date]:
    """Upcoming date with this month/day, or the recent past one when it is far away."""
    upcoming: Optional[date] = None
    past: Optional[date] = None
    for add in (0, 1):
        try:
            candidate = date(base.year + add, month, day)
        except ValueError:
            continue
        if candidate >= base:
            if upcoming is None:
                upcoming = candidate
        elif past is None or candidate > past:
            past = candidate
    if upcoming is not None and (upcoming - base).days <= MAX_LOOKAHEAD_DAYS:
        return upcoming
    return past or upcoming


def _future_day_of_month(base: date, day: int) -> Optional[date]:
    """Nearest day-of-month (this month or a later one) that is not before ``base``."""
    month_index = base.month - 1
    for add in range(0, 3):
        index = month_index + add
        try:
            candidate = date(base.year + index // 12, index % 12 + 1, day)
        except ValueError:
            continue
        if candidate >= base:
            return candidate
    return None


def _at(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime(day.year, day.month, day.day, hour, minute, 0)


def _clock_span(text: str) -> tuple[Optional[str], Optional[str]]:
    span = _CLOCK_SPAN_RE.search(text or "")
    if not span:
        return None, None
    # A bare「11-03」is a date fragment, not a 11:00–03:00 window.
    if not re.search(r"[:：]|点|上午|下午|晚上", span.group(0)):
        return None, None
    first_period, hour1, minute1, second_period, hour2, minute2 = span.groups()
    start = _clock(hour1, minute1, first_period)
    end = _clock(hour2, minute2, second_period)
    # 「下午2点到6点」means 14:00–18:00: the end inherits the afternoon period.
    if start and end and first_period and not second_period:
        if int(start[:2]) >= 12 and int(end[:2]) < 12:
            end = _clock(hour2, minute2, first_period)
    return start, end


def _month_day_span(
    today: date,
    month1: int,
    day1: int,
    month2: int,
    day2: int,
    start_h: Optional[str],
    end_h: Optional[str],
) -> tuple[Optional[datetime], Optional[datetime]]:
    """Resolve「11月20号到22号」/「12-01 到 12-02」against the next upcoming dates."""
    first = _future_month_day(today, month1, day1)
    if first is None:
        return None, None
    last = _future_month_day(first, month2, day2)
    if last is None:
        return None, None
    return (
        _at(first, int(start_h[:2]), int(start_h[3:])) if start_h else _at(first, 9),
        _at(last, int(end_h[:2]), int(end_h[3:])) if end_h else _at(last, 18),
    )


def _parse_leave_span(text: str) -> tuple[Optional[datetime], Optional[datetime]]:
    value = text or ""
    today = now_naive().date()
    start_h, end_h = _clock_span(value)

    ranged = _DATE_TIME_RANGE_RE.search(value) or _DATE_RANGE_RE.search(value)
    if ranged:
        start = _parse_dt(ranged.group(1), end_of_day=False)
        end = _parse_dt(ranged.group(2), end_of_day=True)
        if start_h and end_h:
            start = _at(start.date(), int(start_h[:2]), int(start_h[3:]))
            end = _at(end.date(), int(end_h[:2]), int(end_h[3:]))
        return start, end

    natural = _NATURAL_RANGE_RE.search(value)
    if natural:
        first = today + timedelta(days=_WEEKDAY_OFFSET[natural.group(1)])
        last = today + timedelta(days=_WEEKDAY_OFFSET[natural.group(2)])
        return (
            _at(first, int(start_h[:2]), int(start_h[3:])) if start_h else _at(first, 9),
            _at(last, int(end_h[:2]), int(end_h[3:])) if end_h else _at(last, 18),
        )

    cn = _CN_RANGE_RE.search(value)
    if cn:
        return _month_day_span(
            today, int(cn.group(1)), int(cn.group(2)),
            int(cn.group(3) or cn.group(1)), int(cn.group(4)),
            start_h, end_h,
        )

    md = _MD_RANGE_RE.search(value)
    if md:
        return _month_day_span(
            today, int(md.group(1)), int(md.group(2)), int(md.group(3)), int(md.group(4)),
            start_h, end_h,
        )

    day_range = _DAY_RANGE_RE.search(value)
    if day_range:
        first = _future_day_of_month(today, int(day_range.group(1)))
        if first is None:
            return None, None
        last = _future_day_of_month(first, int(day_range.group(2)))
        if last is None:
            return None, None
        return (
            _at(first, int(start_h[:2]), int(start_h[3:])) if start_h else _at(first, 9),
            _at(last, int(end_h[:2]), int(end_h[3:])) if end_h else _at(last, 18),
        )

    if "今天" in value and start_h and end_h:
        return (
            _at(today, int(start_h[:2]), int(start_h[3:])),
            _at(today, int(end_h[:2]), int(end_h[3:])),
        )
    day_word = next((w for w in ("今天", "明天", "后天") if w in value), "")
    if day_word:
        target = today + timedelta(days=_WEEKDAY_OFFSET[day_word])
        return (
            _at(target, int(start_h[:2]), int(start_h[3:])) if start_h else _at(target, 9),
            _at(target, int(end_h[:2]), int(end_h[3:])) if end_h else _at(target, 18),
        )

    day = _DATE_RE.search(value)
    if day and start_h and end_h:
        parsed = date.fromisoformat(day.group(1))
        return (
            _at(parsed, int(start_h[:2]), int(start_h[3:])),
            _at(parsed, int(end_h[:2]), int(end_h[3:])),
        )
    return None, None


def _heard_reason(message: str) -> str:
    matched = _REASON_RE.search(message or "")
    if matched and matched.group(1).strip():
        return matched.group(1).strip()
    text = (message or "").strip()
    cleaned = re.sub(
        r"(请假类型|开始时间|结束时间|事由)\s*[:：]?\s*",
        " ",
        text,
    )
    cleaned = re.sub(r"\d{4}-\d{2}-\d{2}(?:[T\s]\d{1,2}:\d{2}(?::\d{2})?)?", " ", cleaned)
    cleaned = re.sub(r"\d{1,2}\s*月\s*\d{1,2}\s*(?:号|日)?", " ", cleaned)
    cleaned = re.sub(r"\d{1,2}\s*号+", " ", cleaned)
    cleaned = re.sub(
        r"(?:我)?想要?|我要|帮我|麻烦你?|病假|事假|紧急|请假|到|至|一天|明天|后天|今天",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"[，,。．\s]+", " ", cleaned).strip(" ，,。")
    # Prefer concrete symptom/reason phrases.
    for cue in ("肚子疼", "肚子痛", "发烧", "感冒", "身体不适", "看病", "家里有事"):
        if cue in text:
            return cue
    if cleaned in _REASON_STOPWORDS or len(cleaned) < 2:
        return ""
    return cleaned[:500]


def _clock(hour: str, minute: Optional[str], period: Optional[str]):
    try:
        h = int(hour)
    except (TypeError, ValueError):
        return None
    m = int(minute or "0")
    if period in {"下午", "晚上"} and h < 12:
        h += 12
    if h > 23 or m > 59:
        return None
    return f"{h:02d}:{m:02d}"


def form_reply(message: str, history: list | None = None) -> str:
    kind = _leave_kind(message) or _leave_kind(_last_assistant(history or []))
    missing = _missing_leave_bits(message, history)
    if not kind and "type" in missing:
        return "可以请假。先告诉我是病假、事假还是紧急，顺便说从哪天到哪天、因为什么。"
    if missing:
        hints = []
        if "type" in missing:
            hints.append("假别（病假/事假/紧急）")
        if "time" in missing:
            hints.append("起止日期，比如 2026-11-17 到 2026-11-19")
        if "reason" in missing:
            hints.append("事由")
        lead = f"好，先按{kind}。" if kind else "信息我还差一点点。"
        return lead + "请再补充：" + "、".join(hints) + "。也可以一口气说完，我会直接帮你交。"
    return "可以请假。直接说假别、时间和事由就行。"


def _missing_leave_bits(message: str, history: list | None = None) -> set[str]:
    text = message or ""
    missing: set[str] = set()
    kind = _leave_kind(text) or _leave_kind(_last_assistant(history or []))
    if not kind:
        missing.add("type")
    start, end = _parse_leave_span(text)
    has_time = bool(start and end)
    if not has_time:
        missing.add("time")
    if not _heard_reason(text):
        missing.add("reason")
    return missing


def parse_filled_form(message: str) -> Optional[dict]:
    text = message or ""
    type_m = re.search(r"请假类型\s*[:：]\s*(病假|事假|紧急|sick|personal|emergency)", text)
    if not type_m:
        type_m = _TYPE_RE.search(text)
    start_m = _START_RE.search(text)
    end_m = _END_RE.search(text)
    reason_m = _REASON_RE.search(text)
    if not (type_m and start_m and end_m and reason_m):
        return None
    raw_type = type_m.group(1)
    leave_type = {
        "病假": "sick",
        "sick": "sick",
        "事假": "personal",
        "personal": "personal",
        "紧急": "emergency",
        "emergency": "emergency",
    }[raw_type]
    reason = reason_m.group(1).strip()
    if not reason or reason in {"……", "...", "…"}:
        return None
    try:
        start_time = _parse_dt(start_m.group(1), end_of_day=False)
        end_time = _parse_dt(end_m.group(1), end_of_day=True)
    except BusinessError:
        return None
    return {
        "leave_type": leave_type,
        "start_time": start_time,
        "end_time": end_time,
        "reason": reason[:500],
    }


def _leave_dialogue(
    db: Session, student_id: int, message: str, place: str, history: list | None = None
) -> dict:
    # Enough fields → submit immediately; otherwise ask only for missing bits.
    spoken = _compose_leave_utterance(message, history)
    filled = _natural_leave(spoken, history) or parse_filled_form(spoken)
    form = leave_form(student_id)
    if filled is None or not filled.get("reason"):
        return {
            "reply": form_reply(spoken, history),
            "intent": "leave_form",
            "form": form,
            "data": None,
        }
    if filled["end_time"] <= filled["start_time"]:
        return {
            "reply": "结束时间要晚于开始时间。请再说一次从哪天到哪天。",
            "intent": "leave_form",
            "form": form,
            "data": None,
        }
    if filled["start_time"].date() < now_naive().date():
        return {
            "reply": "开始时间不能早于今天。请再说一次准备从哪天请到哪天。",
            "intent": "leave_form",
            "form": form,
            "data": None,
        }
    payload = StudentLeaveCreate(
        leave_type=filled["leave_type"],
        start_time=filled["start_time"],
        end_time=filled["end_time"],
        reason=filled["reason"],
    )
    try:
        # Locks student row; creates leave + ENT todo via synchronize_source
        row = StudentAdminServiceLayer(db).submit_student_leave(student_id, payload)
    except BusinessError as exc:
        detail = str(exc.detail)
        if "相同时间段" in detail or "重复" in detail:
            hint_start = now_naive().date() + timedelta(days=14)
            hint_end = hint_start + timedelta(days=1)
            detail = (
                detail.rstrip("。")
                + f"。换一组日期再说一次，比如 {hint_start.isoformat()} 到 {hint_end.isoformat()}。"
            )
        return {
            "reply": detail,
            "intent": "leave_form",
            "form": form,
            "data": None,
        }
    label = LEAVE_TYPE_LABEL.get(filled["leave_type"], filled["leave_type"])
    span = _speak_span(filled["start_time"], filled["end_time"])
    teacher_id = StudentAdminRepository(db).class_teacher(student_id)
    if teacher_id:
        _staff_notify(
            db,
            user_id=teacher_id,
            notification_type="leave_pending",
            title="学生请假待审批",
            content=(
                f"学生提交了{label}，{span}，原因：{filled['reason']}。"
                "请到企业助手待办/请假审批处理。"
            ),
            related_type="student_admin_service",
            related_id=row.id,
        )
        db.commit()
    reply = (
        f"已经帮你交上{label}了，{span}，原因是{filled['reason']}。"
        "班主任那边会收到，等他审批就行。"
    )
    return {
        "reply": reply,
        "intent": "leave_submit",
        "form": None,
        "data": _plain(row.model_dump()),
    }


def _leave_query(db: Session, student_id: int) -> dict:
    rows = StudentAdminServiceLayer(db).student_leaves(student_id, None, 3)
    if not rows:
        reply = "你还没有请过假。想请的话直接说「我要请假」，我先让你选类型。"
    else:
        spoken = [_speak_one_leave(row.model_dump()) for row in rows]
        reply = "我帮你看了最近的请假。" + "".join(spoken)
    return {
        "reply": reply,
        "intent": "leave_query",
        "form": None,
        "data": _plain([r.model_dump() for r in rows]),
    }


def _speak_one_leave(row: dict) -> str:
    kind = LEAVE_TYPE_LABEL.get(row.get("leave_type"), "请假")
    status = LEAVE_STATUS_SPOKEN.get(row.get("status"), "处理中")
    return f"{kind}从{_speak_when(row.get('start_time'))}到{_speak_when(row.get('end_time'))}，{status}。"


def _feedback(db: Session, student_id: int, message: str, history: list, place: str) -> dict:
    picked = _picked_feedback(message, history)
    pending_type = _feedback_detail_pending(history)
    if picked is None and pending_type and _has_substance(message):
        picked = (pending_type, "正式投诉" if pending_type == "complaint" else "建议")
    if picked is None:
        return {
            "reply": _care(message) + "\n" + _feedback_choices(),
            "intent": "feedback_choice",
            "form": None,
            "data": {"choices": ["正式投诉", "提建议", "先咨询"]},
        }
    ticket_type, label = picked
    detail = _feedback_detail(message, history)
    if ticket_type == "consult":
        return {
            "reply": f"好，先不记下来。{_care(detail)}你具体想先问哪一部分？",
            "intent": "feedback_choice",
            "form": None,
            "data": {"choice": "consult"},
        }
    if not _has_substance(detail):
        return {
            "reply": (
                f"好，{label}。{_FEEDBACK_DETAIL_CUE}：什么时候、涉及谁、发生了什么？"
                f"你说完我按{label}记下来。"
            ),
            "intent": "feedback_detail",
            "form": None,
            "data": {"ticket_type": ticket_type},
        }
    title = speak(detail, purpose="feedback_title") or feedback_summary(detail)
    # learning → class teacher; company → company assignee (feedback module)
    category: Literal["learning", "company"] = (
        "company" if any(k in detail for k in ("公司", "机构", "中介", "销售")) else "learning"
    )
    payload = StudentComplaintCreate(
        category=category,
        title=title[:80],
        content=(detail or "").strip()[:10000] or feedback_summary(detail),
        ticket_type="suggestion" if ticket_type == "suggestion" else "complaint",
    )
    try:
        row = feedback_service.submit_student_complaint(db, student_id, payload)
    except BusinessError as exc:
        return {
            "reply": str(exc.detail),
            "intent": "feedback",
            "form": None,
            "data": None,
        }
    notify_id = row.assignee_id or (
        StudentAdminRepository(db).class_teacher(student_id) if category == "learning" else None
    )
    if notify_id:
        _staff_notify(
            db,
            user_id=notify_id,
            notification_type="feedback_new",
            title=f"学生{label}",
            content=f"学生提交了{label}：{feedback_summary(detail)}。请在投诉工单跟进。",
            related_type="student_feedback_ticket",
            related_id=row.id,
        )
        db.commit()
    if category == "learning":
        reply = f"好，我按{label}交给老师了，他会跟进。你先安心，有进展会在通知里看到。"
    else:
        reply = f"好，我按{label}交给负责机构事务的老师了，他会跟进。你先安心，有进展会在通知里看到。"
    safe = row.model_dump()
    safe.pop("assignee_id", None)
    return {"reply": reply, "intent": "feedback", "form": None, "data": _plain(safe)}


def _progress(db: Session, student_id: int) -> dict:
    rows = student_service.application_progress(db, student_id, None, 5)
    if not rows:
        reply = "还没有查到你的留学申请进度。"
    else:
        row = rows[0]
        stage = STAGE_LABEL.get(row.stage, "办理中")
        place = row.target_school or "目标院校"
        major = row.target_major or ""
        reply = f"你正在申请{place}{('的' + major) if major else ''}，现在是{stage}。"
        if row.progress_detail:
            detail = row.progress_detail.strip()
            if detail and detail not in reply:
                reply += detail if detail.endswith("。") else detail + "。"
        if row.next_action:
            reply += f"下一步是{row.next_action}。"
    return {
        "reply": reply,
        "intent": "progress",
        "form": None,
        "data": _plain([r.model_dump() for r in rows]),
    }


def _deadline(db: Session, student_id: int) -> dict:
    page = student_service.academic_deadlines(db, student_id, offset=0, limit=10, upcoming=True)
    rows = page.items
    if not rows:
        reply = "最近没有待办考务。"
    else:
        lines = [
            f"{row.title}截止到{_speak_when(row.deadline)}，{DEADLINE_STATUS_LABEL.get(row.status, '还需要留意')}"
            for row in rows
        ]
        reply = "最近要注意：" + "。".join(lines) + "。"
    return {
        "reply": reply,
        "intent": "deadline",
        "form": None,
        "data": _plain([r.model_dump() for r in rows]),
    }


def _psych(db: Session, student_id: int, message: str, history: list | None, place: str) -> dict:
    hits = high_risk_hits(message or "")
    now = now_naive()
    db.execute(
        insert(_psych_record).values(
            student_id=student_id,
            interaction_content=(message or "")[:2000],
            record_date=now.date(),
            create_time=now,
        )
    )
    alert_id = None
    if hits:
        teacher_id = StudentAdminRepository(db).class_teacher(student_id)
        if teacher_id:
            result = db.execute(
                insert(_psych_alert).values(
                    student_id=student_id,
                    teacher_id=teacher_id,
                    risk_level="high",
                    status="pending",
                    trigger_reason=f"对话出现高危表述：{(message or '')[:160]}",
                    create_time=now,
                    update_time=now,
                )
            )
            alert_id = int(result.lastrowid)
            _staff_notify(
                db,
                user_id=teacher_id,
                notification_type="psych_alert",
                title="学生心理高危预警",
                content=(
                    "学生在对话里表达了危险情绪，请尽快私下跟进。"
                    f"原话摘要：{(message or '')[:120]}"
                ),
                related_type="student_psych_alert",
                related_id=alert_id,
            )
        db.commit()
        reply = speak(message, history, place, purpose="psych_crisis") or (
            "听到你这么说，我很担心你。你愿意的话，慢慢跟我说说现在最难受的是什么。"
            "你身边也有人可以帮你，班主任和学校心理支持都可以。"
        )
    else:
        db.commit()
        reply = speak(message, history, place, purpose="psych_care") or (
            "想家、心里不踏实都正常。你要是愿意，我陪你聊聊；需要的话也可以找班主任说一声。"
        )
    # Never expose alert / risk flags to the student-facing payload
    return {
        "reply": reply,
        "intent": "psych",
        "form": None,
        "data": None,
    }


def _ask(
    db: Session,
    student_id: int,
    message: str,
    place: str,
    history: list | None = None,
    memories: list[str] | None = None,
) -> dict:
    policies = student_service.student_policies(db, student_id)
    overseas = student_service.overseas_resources(db, student_id, "", 0, 3)
    facts: list[str] = []
    for tip in (policies.resources or [])[:3]:
        facts.append(f"政策「{tip.title}」：{tip.description}")
    for item in (overseas.get("items") or [])[:3]:
        title = item.get("title") or item.get("question") or "相关说明"
        body = item.get("description") or item.get("answer") or ""
        facts.append(f"海外生活「{title}」：{body}".strip("："))
    if memories:
        facts.extend(f"记忆：{item}" for item in memories[:3])
    grounded = "\n".join(facts)
    spoken = None
    if facts:
        spoken = speak(
            f"学生问：{(message or '').strip()}\n请只用下面已收录资料与记忆作答，不要编造电话地址：\n{grounded[:1800]}",
            history,
            place,
        )
    if spoken:
        reply = spoken
    elif policies.resources:
        tip = policies.resources[0]
        reply = f"按你的留学去向，可以先看「{tip.title}」：{tip.description}"
    elif overseas.get("items"):
        item = overseas["items"][0]
        reply = f"我找到一条海外生活资料：{item.get('title') or item.get('question') or '相关说明'}。"
    else:
        reply = "这类办事问题我暂时没有可靠依据，建议你问班主任或顾问，不要听信不确定的电话地址。"
    return {
        "reply": reply,
        "intent": "ask",
        "form": None,
        "data": {
            "country": policies.country,
            "policy_count": len(policies.resources),
            "overseas_count": len(overseas.get("items") or []),
        },
    }


def _wants_upgrade(message: str) -> bool:
    return any(k in (message or "") for k in ("升学", "读研", "本硕", "硕士", "继续读书", "学历提升"))


def _upgrade_reply(message: str, place: str, history: list) -> dict:
    spoken = speak(message, history, place)
    if not spoken:
        if "新加坡" in place:
            spoken = (
                "如果你想往本硕方向走，新加坡国际本硕升学计划可以看看。"
                "我可以帮你记下意向，建议再约顾问细聊语言和院校匹配。"
            )
        else:
            spoken = (
                "如果你想继续升学，中德精英人才共建计划是常见方向之一。"
                "我可以帮你记下意向，建议先约顾问评估语言成绩和目标院校。"
            )
    return {"reply": spoken, "intent": "upgrade", "form": None, "data": {"place": place}}


def _name_from_memories(memories: list[str] | None) -> str:
    for item in memories or []:
        text = str(item)
        if text.startswith("学生姓名："):
            return text.split("：", 1)[-1].strip()
    return ""


def _chat_reply(
    message: str, place: str, history: list | None = None, memories: list[str] | None = None
) -> str:
    text = (message or "").strip()
    name = _name_from_memories(memories)
    intro = (
        "我是留学学生助手。我可以发请假单、查请假和留学进度、看近期考试截止、记下投诉，"
        f"也可以按你的留学去向（{place}）回答办事问题。你直接说想办的事就行。"
        if place and place != "还没登记"
        else "我是留学学生助手。我可以发请假单、查请假和留学进度、看近期考试截止、记下投诉。你直接说想办的事就行。"
    )
    if any(k in text for k in ("你是谁", "你好", "您好", "在吗", "介绍一下")):
        if name and any(k in text for k in ("你好", "您好", "在吗")):
            return f"{name}，我在。想请假、查进度、看考试截止或投诉，直接说就行。"
        return intro
    # LLM may use memories internally; never dump raw memory lines to the student.
    prompt = text
    if name:
        prompt = f"学生姓名：{name}\n学生本轮说：{text}"
    spoken = speak(prompt, history, place or "还没登记")
    if spoken and "学生说：" not in spoken and "长期记忆" not in spoken and "助手答复要点" not in spoken:
        return spoken
    if any(k in text for k in ("退学", "休学", "转学", "转专业")):
        return "退学和休学我这边不能直接办。你先说说是什么情况，我可以帮你记给班主任。"
    if any(k in text for k in ("宿舍", "环境", "太差", "太吵", "不满")):
        return (
            "宿舍和环境的事我可以帮你记下来。"
            "你回 1 正式投诉，回 2 提建议，回 3 先咨询。"
        )
    if name:
        return f"{name}，我在听。你可以直接说请假、查进度、看考试截止，或者投诉；想聊聊也行。"
    return "我在听。你可以直接说请假、查进度、看考试截止，或者投诉；想聊聊也可以继续说。"


def _staff_notify(
    db: Session,
    *,
    user_id: int,
    notification_type: str,
    title: str,
    content: str,
    related_type: str,
    related_id: int,
) -> None:
    key = f"{notification_type}:{related_type}:{related_id}:{user_id}"
    if db.scalar(select(notification_log.c.id).where(notification_log.c.dedup_key == key)) is not None:
        return
    db.execute(
        insert(notification_log).values(
            user_id=user_id,
            notification_type=notification_type,
            dedup_key=key,
            related_type=related_type,
            related_id=related_id,
            title=title,
            content=content,
            channel="system",
            status="sent",
            create_time=now_naive(),
        )
    )


def _parse_dt(value: str, *, end_of_day: bool = False) -> datetime:
    raw = value.strip().replace(" ", "T")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        raw = raw + ("T18:00:00" if end_of_day else "T09:00:00")
    elif len(raw) == 16:
        raw += ":00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise BusinessError(422, "时间格式不对，请按 2026-11-13 或 2026-11-13T09:00:00 再说一次") from exc


def _fmt(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if value is None:
        return ""
    return str(value).replace("T", " ")[:16]


def _speak_when(value) -> str:
    text = _fmt(value)
    return text if text else "待定时间"


def _speak_span(start, end) -> str:
    return f"从{_speak_when(start)}到{_speak_when(end)}"


def _plain(value: Any):
    if isinstance(value, datetime):
        return value.isoformat(sep=" ", timespec="seconds")
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(v) for v in value]
    return value
