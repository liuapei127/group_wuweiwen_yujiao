"""Stable exam identity and canonical submission payloads."""
import hashlib
import json
from decimal import Decimal


def default_exam_key(course_name, semester, course_id=None):
    identity = course_name.strip().casefold() if course_id is None else f"teaching-course:{course_id}"
    value = json.dumps([identity, (semester or "").strip().casefold()], ensure_ascii=False)
    return "course:" + hashlib.sha256(value.encode()).hexdigest()


def submission_hash(values):
    payload = dict(values)
    if payload.get("course_id") is None:
        payload.pop("course_id", None)
    if payload.get("study_stage", "unspecified") == "unspecified":
        payload.pop("study_stage", None)
    payload["score"] = format(Decimal(str(payload["score"])), ".2f")
    payload["credit"] = None if payload.get("credit") is None else format(Decimal(str(payload["credit"])), ".1f")
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
