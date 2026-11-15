import re

from sqlalchemy.orm import Session

from app.modules.events import service as events
from app.modules.visitor.catalog import matching_courses
from app.modules.visitor.content_service import list_sections

_COUNTRIES = ("德国", "新加坡")
_FIELDS = ("航空", "酒店", "双元制", "护理", "工程", "计算机")
_LEVELS = ("高中", "中职", "大专", "本科", "硕士", "初中")
_EVENT_WORDS = ("活动", "讲座", "说明会", "宣讲", "分享会", "开放日")
_DAYS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "十": 10}
_EVENT_TYPE = {"offline": "线下", "online": "线上", "hybrid": "线上及线下"}


def country_for(query: str) -> str:
    return next((country for country in _COUNTRIES if country in query), "")


def names_event(query: str) -> bool:
    return any(word in query for word in _EVENT_WORDS)


def recommendations(db: Session, query: str) -> list[dict]:
    preferences = [country_for(query)]
    preferences.extend(next((word for word in words if word in query), "") for words in (_FIELDS, _LEVELS))
    terms = list(filter(None, preferences))
    courses = [
        {
            "code": str(row.id), "name": row.project_name, "country": preferences[0],
            "summary": (row.description or "")[:600], "target_audience": row.target_audience,
            "category": row.category, "price": str(row.price) if row.price is not None else None,
        }
        for row in matching_courses(db, terms)
    ]
    if courses or any(preferences[1:]):
        return courses
    return [
        {"code": f"官网栏目-{card.id}", "name": card.title, "country": preferences[0],
         "summary": card.content[:600], "target_audience": None, "category": "官网留学项目", "price": None}
        for section in list_sections(db, published_only=True) if section.anchor == "programs"
        for card in section.cards if not terms or terms[0] in f"{card.title} {card.content}"
    ][:5]


def activity_list(db: Session, query: str) -> list[dict]:
    match = re.search(r"(?:未来|近|接下来)?\s*(\d{1,3}|[一二两三四五六七十])\s*天", query)
    raw = match.group(1) if match else ""
    days = min(90, max(1, int(raw) if raw.isdecimal() else _DAYS.get(raw, 30)))
    event_type = None
    if any(word in query for word in ("线上", "直播", "在线")):
        event_type = "online"
    if any(word in query for word in ("线下", "现场")):
        event_type = "offline"
    rows = events.public_schedule(db, days=days, keyword=country_for(query), event_type=event_type)
    return [
        {
            "event_id": row.id, "event_code": str(row.id), "title": row.event_name,
            "event_type": _EVENT_TYPE[row.event_type], "event_at": row.start_time.isoformat(sep=" ", timespec="minutes"),
            "location": row.location, "seats_left": row.max_participants - row.current_participants,
        }
        for row in rows
    ]
