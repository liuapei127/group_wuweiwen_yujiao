from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy import select

from app.core.exceptions import BusinessError
from app.core.security.authorization import require_permission
from app.modules.auth.models import accounts

from . import report_ai
from .board_service import employee_detail
from .periods import week_monday
from .wellbeing_models import EmployeeReportConflict


class Finding(BaseModel):
    summary: str = Field(min_length=1, max_length=512)
    daily_excerpt: str = Field(min_length=1, max_length=2000)
    weekly_excerpt: str = Field(min_length=1, max_length=2000)


class Findings(BaseModel):
    conflicts: list[Finding] = Field(max_length=10)


class Resolution(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    status: Literal["verified", "dismissed"]
    verify_note: str = Field(min_length=1, max_length=2000)


def _rows(employee_id, anchor):
    return select(EmployeeReportConflict).where(EmployeeReportConflict.employee_id == employee_id,
                                              EmployeeReportConflict.week_start == week_monday(anchor))


def list_findings(db, principal, employee_id, anchor: date):
    employee_detail(db, principal, anchor, "week", employee_id)
    return [{key: getattr(row, key) for key in ("id", "summary", "daily_excerpt", "weekly_excerpt", "status", "verify_note")}
            for row in db.scalars(_rows(employee_id, anchor).order_by(EmployeeReportConflict.id.desc()).limit(100))]


def scan(db, principal, employee_id, anchor: date):
    require_permission(principal, "reports:formal:generate")
    source = employee_detail(db, principal, anchor, "week", employee_id)
    weekly, daily = source["weekly_report"], source["reports"]
    if not weekly or not daily:
        raise BusinessError(422, "需要同一位员工的周报及至少一份日报，才能比对")
    weekly_text = (weekly["content"] + "\n" + (weekly["key_progress"] or ""))[:5000]
    daily_text = [str(row["report_date"]) + " " + (row["content"] + "\n" + str(row["key_progress"] or ""))[:2500]
                  for row in daily]
    db.rollback()
    try:
        findings = Findings.model_validate_json(report_ai.compare_reports(daily_text, weekly_text))
    except ValidationError as exc:
        raise BusinessError(502, "AI 冲突检查输出格式有误") from exc
    db.scalar(select(accounts.c.id).where(accounts.c.id == employee_id).with_for_update())
    employee_detail(db, principal, anchor, "week", employee_id)
    existing = {(r.daily_excerpt, r.weekly_excerpt) for r in db.scalars(_rows(employee_id, anchor))}
    for item in findings.conflicts:
        if item.weekly_excerpt not in weekly_text or not any(item.daily_excerpt in entry for entry in daily_text):
            continue
        pair = (item.daily_excerpt, item.weekly_excerpt)
        if pair not in existing:
            existing.add(pair)
            db.add(EmployeeReportConflict(employee_id=employee_id, week_start=week_monday(anchor),
                                          status="pending", **item.model_dump()))
    db.commit()
    return list_findings(db, principal, employee_id, anchor)


def resolve(db, principal, id, body):
    require_permission(principal, "reports:formal:generate")
    row = db.get(EmployeeReportConflict, id, with_for_update=True)
    if row is None:
        raise BusinessError(404, "冲突事项不存在")
    employee_detail(db, principal, row.week_start, "week", row.employee_id)
    if row.status != "pending":
        raise BusinessError(409, "此事项已核验")
    row.status, row.verify_note = body.status, body.verify_note
    db.commit()
    return {"id": id, "status": body.status}
