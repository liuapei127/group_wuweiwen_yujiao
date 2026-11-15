import re

from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.modules.events import service as events

from .catalog import activity_list, names_event
from .models import CustomerChatSession
from .schemas import PublicChatReply

_CONFIRM = re.compile(r"^(?:我)?(?:确认|确定|就这样)(?:报名|预约|参加)[。！! ]*$")
_PICK = re.compile(r"^(?:(?:我选|选择|选|第|报名编号|活动编号)\s*)+(\d{1,19}|[一二三四五六七八九十])(?:场|号)?[。！! ]*$")
_BOOK = re.compile(r"(?:我要|我想|帮我|麻烦|想)(?:报名|预约|参加)|(?:报名|预约).*(?:活动|讲座|说明会|分享会)")
_NUMBERS = {char: index for index, char in enumerate("一二三四五六七八九十", 1)}


def _pick(query: str, options: list[dict]) -> dict | None:
    found = _PICK.fullmatch(query)
    if found:
        raw = found.group(1)
        number = int(raw) if raw.isdecimal() else _NUMBERS[raw]
        if query.startswith(("活动编号", "报名编号")):
            return next((item for item in options if item["event_id"] == number), None)
        return options[number - 1] if 1 <= number <= len(options) else None
    return next((item for item in options if item["title"] in query), None)


def _offer(db: Session, state: CustomerChatSession, query: str) -> PublicChatReply:
    options = activity_list(db, query)
    state.event_options = options
    state.pending_event_id = None
    if not options:
        return PublicChatReply(answer="这个范围内暂时没有可预约的活动。你可以换个时间或地区，也可以到官网查看活动。")
    lines = [
        f"{i}. {item['title']}（编号 {item['event_code']}，{item['event_type']}）"
        f"，{item['event_at']}，{item['location'] or '地点待公布'}，余 {item['seats_left']} 席"
        for i, item in enumerate(options, start=1)
    ]
    next_step = "回复「第一场」或「活动编号」选择场次。" if state.visitor_id is not None else "请先登录官网，再选择场次完成预约。"
    return PublicChatReply(answer="可预约活动（北京时间）：\n" + "\n".join(lines) + "\n" + next_step)


def booking_reply(db: Session, state: CustomerChatSession, query: str) -> PublicChatReply | None:
    options = state.event_options or []
    pending = next((item for item in options if item["event_id"] == state.pending_event_id), None)
    if _CONFIRM.fullmatch(query):
        if state.visitor_id is None:
            return PublicChatReply(answer="请先登录官网，再选择场次并确认报名。")
        if pending is None:
            return PublicChatReply(answer="请先问「有哪些活动」并选择一个场次，然后回复「确认报名」。")
        try:
            registration = events.reserve(db, pending["event_id"], customer_id=state.visitor_id)
        except BusinessError as exc:
            return PublicChatReply(answer=str(exc.detail))
        label = "已签到" if registration.status == "attended" else "已预约"
        return PublicChatReply(answer=f"{label}「{pending['title']}」，{pending['event_at']}（北京时间）。可在「我的预约」查看。",
                               reservation_changed=True)

    if pending and query in ("取消本次报名", "不报名了", "取消选择", "算了"):
        state.pending_event_id = None
        return PublicChatReply(answer="已清除本次场次选择。你可以重新查询活动。")

    is_activity = names_event(query) or "预约" in query or "报名记录" in query
    if is_activity and any(word in query for word in ("我的", "已约", "预约记录", "报名记录", "预约状态")):
        if state.visitor_id is None:
            return PublicChatReply(answer="请登录官网查看你的预约记录。")
        statuses = {"registered": "已预约", "cancelled": "已取消", "attended": "已签到", "no_show": "未到场"}
        rows = events.visitor_reservations(db, state.visitor_id, None, 5)
        lines = [f"{row.event.event_name}：{statuses.get(row.reservation.status, row.reservation.status)}" for row in rows]
        return PublicChatReply(answer="最近的预约记录：\n" + "\n".join(lines) if lines else "当前账号还没有活动预约记录。")

    if is_activity and any(word in query for word in ("怎样", "怎么", "如何", "取消预约")):
        return PublicChatReply(answer="登录后，问我「有哪些活动」，选好场次再回复「确认报名」。也可以打开官网「活动预约」直接办理，在「我的预约」查看或取消。")

    picked = _pick(query, options)
    if picked:
        if state.visitor_id is None:
            return PublicChatReply(answer=f"你选择的是「{picked['title']}」。请先登录官网完成预约。")
        state.pending_event_id = picked["event_id"]
        return PublicChatReply(answer=f"你选择了「{picked['title']}」，{picked['event_at']}（北京时间）。请回复「确认报名」完成预约。")
    if _PICK.fullmatch(query):
        return PublicChatReply(answer="没有找到这个场次，请先查询活动并使用列表里的序号或活动编号。")
    if names_event(query) or _BOOK.search(query):
        listing = _offer(db, state, query)
        picked = _pick(query, state.event_options or [])
        if picked and _BOOK.search(query) and state.visitor_id is not None:
            state.pending_event_id = picked["event_id"]
            return PublicChatReply(answer=f"你选择了「{picked['title']}」，{picked['event_at']}（北京时间）。请回复「确认报名」完成预约。")
        return listing
    return None
