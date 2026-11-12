"""Convert database snapshots into JSON values without an HTTP dependency."""
import json
from datetime import date, datetime
from decimal import Decimal


def _default(value):
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Unsupported snapshot type: {type(value).__name__}")


def json_snapshot(value):
    return json.loads(json.dumps(value, default=_default, ensure_ascii=False))
