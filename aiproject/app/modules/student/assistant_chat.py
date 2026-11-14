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
from datetime import datetime
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
_TYPE_RE = re.compile(r"请假类型\s*[:：]\s*(病假|事假|紧急|sick|personal|emergency)")
_START_RE = re.compile(
    r"开始时间\s*[:：]\s*(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?)"
)
_END_RE = re.compile(
    r"结束时间\s*[:：]\s*(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(?::\d{2})?)"
)
_REASON_RE = re.compile(r"事由\s*[:：]\s*(.+)")
_HIGH_RISK = ("自杀", "不想活", "结束生命", "伤害自己", "轻生")

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
) -> dict:
    turns = history or []
    place = _place_label(db, student_id, mock_country)
    forced, spoken = _follow_choice(message, turns)
    if forced == "leave":
        return _pack(_leave_dialogue(db, student_id, spoken, place))
    if forced == "feedback":
        return _pack(_feedback(db, student_id, spoken, turns, place))
    intent = route(message)["intent"]
    if _picked_feedback(message, turns) or intent == "feedback":
        return _pack(_feedback(db, student_id, message, turns, place))
    if intent == "leave_create":
        return _pack(_leave_dialogue(db, student_id, message, place))
    if intent == "leave_query":
        return _pack(_leave_query(db, student_id))
    if intent == "progress":
        return _pack(_progress(db, student_id))
    if intent == "deadline":
        return _pack(_deadline(db, student_id))
    if intent == "psych":
        return _pack(_psych(db, student_id, message, turns, place))
    if intent == "ask":
        return _pack(_ask(db, student_id, message, place, turns))
    if _wants_upgrade(message):
        return _pack(_upgrade_reply(message, place, turns))
    return _pack(
        {
            "reply": _chat_reply(message, place, turns),
            "intent": "chat",
            "form": None,
            "data": {"place": place},
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
    if "病假" in text or "生病" in text:
        return "病假"
    if "紧急" in text:
        return "紧急"
    if "事假" in text:
        return "事假"
    return ""


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
        if turn.get("role") == "assistant":
            return (turn.get("content") or "").strip()
    return ""


def _changed_topic(message: str) -> bool:
    intent = route(message)["intent"]
    return intent not in {"other"}


def _follow_choice(message: str, history: list):
    last = _last_assistant(history)
    number = _choice_index(message)
    in_leave = ("先选一种" in last and "病假" in last) or (
        "请假类型" in last and "病假" in last
    )
    in_feedback = _feedback_menu_open(history)
    if (in_leave or in_feedback) and not number and _changed_topic(message):
        return None, message
    if in_leave:
        kind = {"1": "病假", "2": "事假", "3": "紧急"}.get(number) or _leave_kind(message)
        if kind and number:
            return "leave", kind
        if kind:
            return "leave", f"{kind}。{message}" if message.strip() not in kind else kind
        return "leave", message
    if in_feedback:
        return "feedback", message
    return None, message


def _natural_leave(message: str) -> Optional[dict]:
    kind = _leave_kind(message)
    if not kind:
        return None
    day = re.search(r"(\d{4}-\d{2}-\d{2})", message or "")
    span = re.search(
        r"(\d{1,2})(?::(\d{2}))?\s*(上午|下午|晚上)?\s*[到至\-–—]\s*(\d{1,2})(?::(\d{2}))?\s*(上午|下午|晚上)?",
        message or "",
    )
    if not day or not span:
        return None
    start_h = _clock(span.group(1), span.group(2), span.group(3))
    end_h = _clock(span.group(4), span.group(5), span.group(6))
    if start_h is None or end_h is None:
        return None
    reason = _heard_reason(message)
    if not reason:
        return None
    return {
        "leave_type": {"病假": "sick", "事假": "personal", "紧急": "emergency"}[kind],
        "start_time": datetime.fromisoformat(f"{day.group(1)}T{start_h}:00"),
        "end_time": datetime.fromisoformat(f"{day.group(1)}T{end_h}:00"),
        "reason": reason[:500],
    }


def _heard_reason(message: str) -> str:
    matched = _REASON_RE.search(message or "")
    if matched and matched.group(1).strip():
        return matched.group(1).strip()
    if any(cue in (message or "") for cue in ("因为", "家里", "生病", "有事")):
        return (message or "").strip()
    return ""


def _clock(hour: str, minute: Optional[str], period: Optional[str]):
    try:
        h = int(hour)
    except (TypeError, ValueError):
        return None
    m = int(minute or "0")
    if period in {"下午", "晚上"} and h < 12:
        h += 12
    if period == "上午" and h == 12:
        h = 0
    if h > 23 or m > 59:
        return None
    return f"{h:02d}:{m:02d}"


def form_reply(message: str) -> str:
    kind = _leave_kind(message)
    natural = _natural_leave(message)
    if natural:
        label = LEAVE_TYPE_LABEL.get(natural["leave_type"], "请假")
        return (
            f"可以，按{label}帮你准备。请按下面四行发给我，时间不要空着：\n"
            f"请假类型：{label}\n"
            f"开始时间：{_fmt(natural['start_time'])}\n"
            f"结束时间：{_fmt(natural['end_time'])}\n"
            f"事由：{natural['reason']}"
        )
    if kind:
        return (
            f"好，先按{kind}。请按下面四行发给我：\n"
            f"请假类型：{kind}\n开始时间：2026-11-13T09:00:00\n"
            f"结束时间：2026-11-13T18:00:00\n事由：……"
        )
    return "可以请假。先选一种：1. 病假 2. 事假 3. 紧急"


def parse_filled_form(message: str) -> Optional[dict]:
    type_m = _TYPE_RE.search(message or "")
    start_m = _START_RE.search(message or "")
    end_m = _END_RE.search(message or "")
    reason_m = _REASON_RE.search(message or "")
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
    if not reason:
        return None
    try:
        start_time = _parse_dt(start_m.group(1))
        end_time = _parse_dt(end_m.group(1))
    except BusinessError:
        return None
    return {
        "leave_type": leave_type,
        "start_time": start_time,
        "end_time": end_time,
        "reason": reason[:500],
    }


def _leave_dialogue(db: Session, student_id: int, message: str, place: str) -> dict:
    # Natural language only drafts the form; submit only after the four-line confirmation.
    filled = parse_filled_form(message)
    form = leave_form(student_id)
    if filled is None or not filled.get("reason"):
        return {
            "reply": form_reply(message),
            "intent": "leave_form",
            "form": form,
            "data": None,
        }
    if filled["end_time"] <= filled["start_time"]:
        return {
            "reply": "结束时间要晚于开始时间。请再说一次从几点到几点。\n" + form_reply(message),
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
        return {
            "reply": str(exc.detail),
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
    hits = [k for k in _HIGH_RISK if k in (message or "")]
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


def _ask(db: Session, student_id: int, message: str, place: str, history: list | None = None) -> dict:
    policies = student_service.student_policies(db, student_id)
    overseas = student_service.overseas_resources(db, student_id, "", 0, 3)
    facts: list[str] = []
    for tip in (policies.resources or [])[:3]:
        facts.append(f"政策「{tip.title}」：{tip.description}")
    for item in (overseas.get("items") or [])[:3]:
        title = item.get("title") or item.get("question") or "相关说明"
        body = item.get("description") or item.get("answer") or ""
        facts.append(f"海外生活「{title}」：{body}".strip("："))
    grounded = "\n".join(facts)
    spoken = None
    if facts:
        spoken = speak(
            f"学生问：{(message or '').strip()}\n请只用下面已收录资料作答，不要编造电话地址：\n{grounded[:1800]}",
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


def _chat_reply(message: str, place: str, history: list | None = None) -> str:
    text = (message or "").strip()
    intro = (
        "我是留学学生助手。我可以发请假单、查请假和留学进度、看近期考试截止、记下投诉，"
        f"也可以按你的留学去向（{place}）回答办事问题。你直接说想办的事就行。"
        if place and place != "还没登记"
        else "我是留学学生助手。我可以发请假单、查请假和留学进度、看近期考试截止、记下投诉。你直接说想办的事就行。"
    )
    if any(k in text for k in ("你是谁", "你好", "您好", "在吗", "介绍一下")):
        return intro
    spoken = speak(text, history, place or "还没登记")
    if spoken:
        return spoken
    if any(k in text for k in ("退学", "休学", "转学", "转专业")):
        return "退学和休学我这边不能直接办。你先说说是什么情况，我可以帮你记给班主任。"
    return "这句话我还没对上要办的事。你可以直接说请假、查进度、看考试截止，或者投诉。"


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


def _parse_dt(value: str) -> datetime:
    raw = value.strip().replace(" ", "T")
    if len(raw) == 16:
        raw += ":00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError as exc:
        raise BusinessError(422, "时间格式不对，请按 2026-11-13T09:00:00 再发一次") from exc


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
