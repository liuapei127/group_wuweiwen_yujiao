import re
from typing import Literal

from sqlalchemy.orm import Session

from app.modules.events import service as events
from app.modules.visitor.catalog import matching_courses
from app.modules.visitor.content_service import list_sections

_COUNTRIES = ("德国", "新加坡")
_FIELDS = ("航空", "酒店", "双元制", "护理", "工程", "计算机")
_LANGUAGES = ("德语", "英语", "语言")
_EDUCATION = {
    "初中": ("初中",), "高中": ("高中",), "中职": ("中职", "中专", "职高", "中技"),
    "大专": ("大专", "专科"), "本科": ("本科",), "硕士": ("硕士",),
}
_EDUCATION_ALIAS = {alias: level for level, aliases in _EDUCATION.items() for alias in aliases}
_LEVEL_WORDS = "|".join(_EDUCATION_ALIAS)
_LEVEL_MENTION = re.compile(_LEVEL_WORDS)
_CURRENT_LEVEL = re.compile(rf"({_LEVEL_WORDS})(?:在读|毕业|学历|生)")
# Public cards can list an audience and individual paths, or use a heading followed by bullets.
_PATH_LINE = re.compile(
    rf"^(?:[•·-]\s*)?(?:招生对象[：:]\s*)?(?:应往届|应届|往届)?"
    rf"(?P<level>{_LEVEL_WORDS})(?:毕业生|在读学生|毕业|在读|学生|学历|生)"
    r"(?:(?:可了解|可参考)(?:以下[^：:]{0,24})?)?(?:\s*[：:]\s*|\s+)(?P<summary>.*)$"
)
_NEGATED_AUDIENCE = re.compile(r"不(?:招收|招生|接受|接收|适合|面向|限|含|包括|可|符合)|禁止|排除|除外")
_LANGUAGE_COURSE = re.compile(r"^(德语|英语|语言)(?:课|课程)$")
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
    if "课程" in query or is_language_course(query):
        return "course"
    return None


def asks_for_catalog_list(query: str) -> bool:
    return _CATALOG_LIST.search(query) is not None


def is_language_course(query: str) -> bool:
    return _LANGUAGE_COURSE.fullmatch(query.strip().rstrip("？?。！!")) is not None


def education_for(query: str) -> str:
    if match := _CURRENT_LEVEL.search(query):
        return _EDUCATION_ALIAS[match.group(1)]
    match = _LEVEL_MENTION.search(query)
    return _EDUCATION_ALIAS[match.group()] if match else ""


def _path_summaries(content: str, education: str, field: str) -> list[str]:
    selected = False
    paths = []
    for raw in content.splitlines():
        line = raw.strip()
        if match := _PATH_LINE.fullmatch(line):
            selected = _EDUCATION_ALIAS[match["level"]] == education
            summary = match["summary"].strip()
        elif selected and line.startswith(("•", "·", "- ")):
            summary = line[1:].strip()
        else:
            selected = False
            continue
        if selected and summary and (not field or field in summary):
            paths.append(summary)
    return paths


def _includes_audience(audience: str, aliases: tuple[str, ...]) -> bool:
    return any(
        not _NEGATED_AUDIENCE.search(clause) and any(alias in clause for alias in aliases)
        for clause in re.split(r"[，。；;,.\n]", audience)
    )


def recommendations(db: Session, query: str) -> list[dict]:
    country = country_for(query)
    kind = catalog_kind(query) or "project"
    if kind == "course":
        language = next((word for word in _LANGUAGES if word in query), "")
        terms = [term for term in (country, language) if term]
        return _catalog_rows(db, country, terms, kind)
    field = next((word for word in _FIELDS if word in query), "")
    education = education_for(query)
    terms = [term for term in (country, field) if term]
    cards = [card for section in list_sections(db, published_only=True) if section.anchor == "programs"
             for card in section.cards]
    exact = _catalog_rows(db, country, terms, kind, cards, education=education, field=field)
    if exact or not country or not (field or education):
        return exact
    return [
        {**row, "summary": "", "target_audience": None, "matches_preferences": False}
        for row in _catalog_rows(db, country, [country], kind, cards)
    ]


def _catalog_rows(db: Session, country: str, terms: list[str], kind: CatalogKind, cards=(), *,
                  education: str = "", field: str = "") -> list[dict]:
    aliases = _EDUCATION.get(education, ())
    rows = [
        {
            "code": str(row.id), "name": row.project_name, "country": country,
            "summary": (row.description or "")[:600], "target_audience": row.target_audience,
            "category": row.category, "matches_preferences": True,
        }
        for row in matching_courses(db, terms, kind=kind, limit=50 if aliases else 5, audience_terms=aliases)
        if not aliases or _includes_audience(row.target_audience or "", aliases)
    ][:5]
    names = {row["name"] for row in rows}
    for card in cards:
        if card.title in names or not all(term in f"{card.title} {card.content}" for term in terms):
            continue
        paths = _path_summaries(card.content, education, field if field not in card.title else "") if education else []
        if education and not paths:
            continue
        rows.append({
            "code": f"官网栏目-{card.id}", "name": card.title, "country": country,
            "summary": ("\n".join(f"  - {path}" for path in paths) if paths else card.content)[:600],
            "target_audience": f"{education}相关招生对象" if paths else None,
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
