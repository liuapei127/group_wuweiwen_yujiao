import re
from typing import Literal

from sqlalchemy.orm import Session

from app.modules.events import service as events
from app.modules.visitor.catalog import matching_courses
from app.modules.visitor.content_service import list_sections

_COUNTRIES = ("德国", "新加坡")
_FIELDS = ("航空", "酒店", "双元制", "护理", "工程", "计算机")
_LANGUAGES = ("德语", "英语", "语言")
_LEVELS = ("高中", "中职", "大专", "本科", "硕士", "初中")
_CATALOG_FOCUS = re.compile(r"(?:问的?是|想了解的?是|要的?是|只(?:问|看|查|要))[^，。！？、,?!]{0,8}?(项目|课程)")
_CATALOG_FOLLOWUP = re.compile(r"^(?:(?:德国|新加坡)\s*)?(?:那|那么)?(?:留学|教学)?(项目|课程)呢[\s？?。!！]*$")
_CATALOG_LIST = re.compile(r"(?:什么|哪些|哪几个)[^，。！？、,?!]{0,8}?(项目|课程)")
CatalogKind = Literal["project", "course"]
_EVENT_WORDS = ("活动", "讲座", "说明会", "宣讲", "分享会", "开放日")
_DAYS = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "十": 10}
_EVENT_TYPE = {"offline": "线下", "online": "线上", "hybrid": "线上及线下"}


def country_for(query: str) -> str:
    return next((country for country in _COUNTRIES if country in query), "")


def names_event(query: str) -> bool:
    return any(word in query for word in _EVENT_WORDS)


def catalog_followup_kind(query: str) -> CatalogKind | None:
    matches = list(_CATALOG_FOCUS.finditer(query))
    match = matches[-1] if matches else _CATALOG_FOLLOWUP.fullmatch(query)
    if match is None:
        return None
    return "project" if match.group(1) == "项目" else "course"


def catalog_kind(query: str) -> CatalogKind | None:
    if focus := catalog_followup_kind(query):
        return focus
    if listing := _CATALOG_LIST.search(query):
        return "project" if listing.group(1) == "项目" else "course"
    if "项目" in query:
        return "project"
    if "课程" in query:
        return "course"
    return None


def asks_for_catalog_list(query: str) -> bool:
    return _CATALOG_LIST.search(query) is not None


def recommendations(db: Session, query: str) -> list[dict]:
    country = country_for(query)
    kind = catalog_kind(query) or "project"
    preferences = [next((word for word in words if word in query), "")
                   for words in ((_LANGUAGES,) if kind == "course" else (_FIELDS, _LEVELS))]
    terms = [term for term in (country, *preferences) if term]
    if kind == "course":
        return _catalog_rows(db, country, terms, kind)
    cards = [card for section in list_sections(db, published_only=True) if section.anchor == "programs"
             for card in section.cards]
    exact = _catalog_rows(db, country, terms, kind, cards)
    if exact or not country or len(terms) == 1:
        return exact
    return [{**row, "matches_preferences": False} for row in _catalog_rows(db, country, [country], kind, cards)]


def _catalog_rows(db: Session, country: str, terms: list[str], kind: CatalogKind, cards=()) -> list[dict]:
    rows = [
        {
            "code": str(row.id), "name": row.project_name, "country": country,
            "summary": (row.description or "")[:600], "target_audience": row.target_audience,
            "category": row.category, "matches_preferences": True,
        }
        for row in matching_courses(db, terms, kind=kind)
    ]
    names = {row["name"] for row in rows}
    for card in cards:
        if card.title in names or not all(term in f"{card.title} {card.content}" for term in terms):
            continue
        rows.append({
            "code": f"官网栏目-{card.id}", "name": card.title, "country": country,
            "summary": card.content[:600], "target_audience": None,
            "category": "官网留学项目", "matches_preferences": True,
        })
        names.add(card.title)
    return rows[:5]


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
