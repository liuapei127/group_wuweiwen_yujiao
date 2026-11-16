"""Keyword intent router for the spoken student assistant."""

from .assistant_safety import PSYCH_CARE_TERMS, high_risk_hits


def route(query: str) -> dict:
    text = (query or "").strip()
    # Explicit harm phrases first; soft mood words must not outrank leave/progress.
    leave_status = any(
        k in text
        for k in ["请假状态", "批了吗", "我的请假", "请假进度", "假批", "请的什么假", "上次请假", "请过什么假"]
    )
    leave_create = any(k in text for k in ["请假", "病假", "事假"]) or (
        "紧急" in text and any(k in text for k in ["假", "请假"])
    )
    progress = any(
        k in text
        for k in ["留学进度", "申请进度", "申请到哪", "查进度"]
    ) or ("进度" in text and "请假" not in text)

    complaintish = any(
        k in text
        for k in ["投诉", "反馈", "工单", "环境太差", "太差了", "态度差", "服务差", "太吵", "卫生差", "不满意"]
    )
    if high_risk_hits(text):
        intent = "psych"
    elif leave_status:
        intent = "leave_query"
    elif leave_create:
        intent = "leave_create"
    elif complaintish:
        intent = "feedback"
    elif progress:
        intent = "progress"
    elif any(k in text for k in ["截止", "DDL", "考务", "德语考试"]):
        intent = "deadline"
    elif any(k in text for k in PSYCH_CARE_TERMS):
        intent = "psych"
    elif any(k in text for k in ["怎么办", "怎么", "挂号", "签证", "交通", "公交", "地铁", "租房", "住宿", "宿舍", "保险", "看病"]):
        intent = "ask"
    else:
        intent = "other"

    if "病" in text:
        leave_type = "sick"
    elif "紧急" in text:
        leave_type = "emergency"
    else:
        leave_type = "personal"
    reason = text[:500] if text else "聊天留言"
    return {"intent": intent, "leave_type": leave_type, "reason": reason}
