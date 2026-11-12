"""Stable exam identity and canonical submission payloads."""
import hashlib
import json
from decimal import Decimal


def default_exam_key(course_name, semester):
    value = json.dumps([course_name.strip().casefold(), (semester or "").strip().casefold()], ensure_ascii=False)
    return "course:" + hashlib.sha256(value.encode()).hexdigest()


def submission_hash(values):
    payload = dict(values)
    payload["score"] = format(Decimal(str(payload["score"])), ".2f")
    payload["credit"] = None if payload.get("credit") is None else format(Decimal(str(payload["credit"])), ".1f")
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
