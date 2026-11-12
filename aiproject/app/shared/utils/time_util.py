from datetime import datetime


def now_naive() -> datetime:
    return datetime.now().replace(microsecond=0)
