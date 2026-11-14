from datetime import date, timedelta


def week_monday(anchor: date) -> date:
    return anchor - timedelta(days=anchor.weekday())


def week_bounds(anchor: date) -> tuple[date, date]:
    monday = week_monday(anchor)
    return monday, monday + timedelta(days=6)
