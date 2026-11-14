from datetime import date, datetime, timedelta, timezone


def week_monday(anchor: date) -> date:
    return anchor - timedelta(days=anchor.weekday())


def week_bounds(anchor: date) -> tuple[date, date]:
    monday = week_monday(anchor)
    return monday, monday + timedelta(days=6)


def beijing_now() -> datetime:
    return datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None, microsecond=0)
