from datetime import datetime, time, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import BigInteger, Date, DateTime, String, Text, column, func, insert, select, table, update
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.security import EmployeePrincipal
from app.core.security.authorization import require_permission, require_student_scope
from app.modules.student_admin.repository import StudentAdminRepository
from app.shared.utils.time_util import now_naive

_alert = table(
    "student_psych_alert", column("id", BigInteger), column("student_id", BigInteger),
    column("teacher_id", BigInteger), column("risk_level", String), column("status", String),
    column("trigger_reason", Text), column("follow_record", Text), column("create_time", DateTime),
    column("update_time", DateTime), column("resolved_time", DateTime),
)


_observation = table(
    "student_psych_record", column("id", BigInteger), column("student_id", BigInteger),
    column("interaction_content", Text), column("record_date", Date), column("create_time", DateTime),
)


class AlertOut(BaseModel):
    id: int
    student_id: int
    risk_level: str
    status: str
    trigger_reason: str
    follow_record: str | None
    create_time: datetime


class AlertUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    status: Literal["following", "resolved", "dismissed"]
    follow_record: str = Field(min_length=1, max_length=10000)


def _owned_query(principal: EmployeePrincipal):
    return select(*(getattr(_alert.c, name) for name in AlertOut.model_fields)).where(
        _alert.c.teacher_id == principal.employee_id, _alert.c.student_id.in_(principal.student_ids),
    )


def list_alerts(db: Session, principal: EmployeePrincipal, before_id: int | None, limit: int) -> list[AlertOut]:
    require_permission(principal, "student-alerts:read")
    query = _owned_query(principal)
    if before_id is not None:
        query = query.where(_alert.c.id < before_id)
    rows = db.execute(query.order_by(_alert.c.id.desc()).limit(limit)).mappings()
    return [AlertOut.model_validate(row) for row in rows]


def follow_alert(db: Session, principal: EmployeePrincipal, alert_id: int, payload: AlertUpdate) -> AlertOut:
    require_permission(principal, "student-alerts:write")
    query = _owned_query(principal).where(_alert.c.id == alert_id)
    try:
        old = db.execute(query.with_for_update()).mappings().one_or_none()
        if old is None:
            raise BusinessError(404, "预警记录不存在")
        if old["status"] not in {"pending", "following"}:
            raise BusinessError(409, "该预警已结案")
        now = now_naive()
        follow_record = "\n".join(part for part in (old["follow_record"], payload.follow_record) if part)
        if len(follow_record.encode("utf-8")) > 60_000:
            raise BusinessError(422, "跟进记录超过可保存长度")
        db.execute(update(_alert).where(_alert.c.id == alert_id).values(
            status=payload.status, follow_record=follow_record, update_time=now,
            resolved_time=now if payload.status != "following" else None,
        ))
        result = AlertOut.model_validate(db.execute(query.with_for_update()).mappings().one())
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


class AlertCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    student_id: int = Field(strict=True, ge=1)
    risk_level: Literal["low", "medium", "high"]
    trigger_reason: str = Field(min_length=1, max_length=10000)


def create_alert(db: Session, principal: EmployeePrincipal, payload: AlertCreate) -> AlertOut:
    require_student_scope(principal, payload.student_id, "student-alerts:write")
    try:
        if not StudentAdminRepository(db).lock_student(payload.student_id):
            raise BusinessError(404, "学生档案不存在或已停用")
        now = now_naive()
        db.execute(insert(_observation).values(
            student_id=payload.student_id, interaction_content=payload.trigger_reason,
            record_date=now.date(), create_time=now,
        ))
        result = db.execute(insert(_alert).values(
            **payload.model_dump(), teacher_id=principal.employee_id, status="pending",
            create_time=now, update_time=now,
        ))
        item = AlertOut(
            **payload.model_dump(), id=result.lastrowid, status="pending",
            follow_record=None, create_time=now,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return item


def weekly_alerts(db: Session, principal: EmployeePrincipal, anchor) -> dict:
    from app.modules.statistics import periods

    require_permission(principal, "student-alerts:read")
    start, end = periods.week_bounds(anchor)
    stmt = select(_alert.c.status, _alert.c.risk_level, func.count()).where(
        _alert.c.teacher_id == principal.employee_id, _alert.c.student_id.in_(principal.student_ids),
        _alert.c.create_time >= datetime.combine(start, time.min),
        _alert.c.create_time < datetime.combine(end + timedelta(days=1), time.min),
    ).group_by(_alert.c.status, _alert.c.risk_level)
    return {"period_start": start, "period_end": end, "items": [
        {"status": status, "risk_level": risk, "count": count} for status, risk, count in db.execute(stmt)
    ]}
