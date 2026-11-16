from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.security.authorization import require_permission, require_student_scope
from app.modules.student import alerts

from . import report_ai, scheduled_repository
from .periods import beijing_now, week_bounds
from .wellbeing_models import WellbeingCase, WellbeingCheckin, WellbeingConsent, WellbeingEvent, WellbeingFollowup

CONSENT_VERSION = "v1"
CONSENT_TEXT = "你的自评用于学生关怀和授权范围内的群体周报。撤回授权后，后续周报将不再纳入你的自评。"
MIN_GROUP = 5


class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ConsentInput(Input):
    granted: bool
    version: Literal["v1"]


class CheckinInput(Input):
    emotion: Literal["very_good", "good", "neutral", "poor", "very_poor"]
    stress: Literal["none", "light", "moderate", "high"]


class CareInput(Input):
    note: str = Field(min_length=1, max_length=2000)


class StaffCareInput(CareInput):
    student_id: int = Field(gt=0)


class FollowupInput(CareInput):
    status: Literal["open", "following", "closed"]


class EventInput(CareInput):
    title: str = Field(min_length=1, max_length=100)
    day: date


class ReportInput(Input):
    anchor: date
    include_ai: bool = False


class ReviewInput(Input):
    suggestion: str = Field(min_length=1, max_length=4000)


def student_panel(db, student_id):
    consent = db.get(WellbeingConsent, student_id)
    checkins = select(WellbeingCheckin).where(WellbeingCheckin.student_id == student_id).order_by(
        WellbeingCheckin.day.desc()).limit(14)
    return {"version": CONSENT_VERSION, "description": CONSENT_TEXT, "granted": bool(consent and consent.granted),
            "checkins": [{"day": row.day, "emotion": row.emotion, "stress": row.stress}
                         for row in db.scalars(checkins)]}


def save_consent(db, student_id, body):
    row = db.get(WellbeingConsent, student_id, with_for_update=True)
    if row is None:
        row = WellbeingConsent(student_id=student_id)
        db.add(row)
    row.granted, row.version, row.updated_at = body.granted, body.version, beijing_now()
    db.commit()
    return {"granted": body.granted}


def save_checkin(db, student_id, body):
    consent = db.get(WellbeingConsent, student_id, with_for_update=True)
    if not consent or not consent.granted or consent.version != CONSENT_VERSION:
        raise BusinessError(403, "请先同意当前自评授权")
    now = beijing_now()
    row = db.get(WellbeingCheckin, (student_id, now.date()), with_for_update=True)
    if row is None:
        row = WellbeingCheckin(student_id=student_id, day=now.date())
        db.add(row)
    row.emotion, row.stress, row.updated_at = body.emotion, body.stress, now
    db.commit()
    return {"day": now.date()}


def desk_week(db: Session, principal, anchor: date):
    require_permission(principal, "student-alerts:read")
    start, end = week_bounds(anchor)
    population = set(principal.student_ids)
    consented = set(db.scalars(select(WellbeingConsent.student_id).where(
        WellbeingConsent.student_id.in_(population), WellbeingConsent.granted.is_(True),
        WellbeingConsent.version == CONSENT_VERSION,
    )))
    check = WellbeingCheckin
    filters = (check.student_id.in_(consented), check.day.between(start, end))
    participants = db.scalar(select(func.count(distinct(check.student_id))).where(*filters))
    data = {**alerts.weekly_alerts(db, principal, anchor), "eligible": len(population),
            "participants": participants if participants >= MIN_GROUP else None, "suppressed": participants < MIN_GROUP, "emotion": [], "stress": []}
    if not data["suppressed"]:
        for key in ("emotion", "stress"):
            field = getattr(check, key)
            # Suppress chart cells with too few distinct participants.
            count = func.count(distinct(check.student_id))
            groups = db.execute(select(check.day, field, count).where(*filters).group_by(
                check.day, field).having(count >= MIN_GROUP).order_by(check.day, field))
            data[key] = [{"day": day, "label": tag, "count": count} for day, tag, count in groups]
    return data


def _case_view(row):
    return {"id": row.id, "student_id": row.student_id, "status": row.status, "note": row.note,
            "assigned_to": row.assigned_to, "created_at": row.created_at}


def open_case(db, student_id, note, assignee=None):
    row = WellbeingCase(student_id=student_id, note=note, assigned_to=assignee,
                        status="open", created_at=beijing_now())
    db.add(row)
    db.flush()
    result = {"id": row.id, "status": row.status}
    db.commit()
    return result


def staff_cases(db, principal, offset, limit):
    require_permission(principal, "student-alerts:write")
    stmt = select(WellbeingCase).where(WellbeingCase.student_id.in_(principal.student_ids)).order_by(
        WellbeingCase.id.desc()).offset(offset).limit(limit + 1)
    rows = list(db.scalars(stmt))
    return {"items": [_case_view(row) for row in rows[:limit]], "has_more": len(rows) > limit}


def case_detail(db, principal, case_id):
    require_permission(principal, "student-alerts:write")
    row = db.get(WellbeingCase, case_id)
    if row is None or row.student_id not in principal.student_ids:
        raise BusinessError(404, "关怀个案不存在")
    actions = db.scalars(select(WellbeingFollowup).where(WellbeingFollowup.case_id == case_id).order_by(
        WellbeingFollowup.id.desc()).limit(100))
    return {**_case_view(row), "followups": [
        {"note": item.note, "actor_id": item.actor_id, "created_at": item.created_at} for item in actions
    ]}


def followup(db, principal, case_id, body):
    require_permission(principal, "student-alerts:write")
    row = db.get(WellbeingCase, case_id, with_for_update=True)
    if row is None or row.student_id not in principal.student_ids:
        raise BusinessError(404, "关怀个案不存在")
    if row.status == "closed":
        raise BusinessError(409, "关怀个案已结案")
    row.status = body.status
    row.assigned_to = principal.employee_id
    db.add(WellbeingFollowup(case_id=case_id, actor_id=principal.employee_id, note=body.note, created_at=beijing_now()))
    db.commit()
    return {"id": case_id, "status": body.status}


def events(db, principal):
    return [{"id": row.id, "title": row.title, "day": row.day, "note": row.note} for row in db.scalars(
        select(WellbeingEvent).where(WellbeingEvent.employee_id == principal.employee_id).order_by(
            WellbeingEvent.day.desc(), WellbeingEvent.id.desc()).limit(100)
    )]


def make_event(db, principal, body):
    row = WellbeingEvent(employee_id=principal.employee_id, **body.model_dump())
    db.add(row)
    db.flush()
    result = {"id": row.id}
    db.commit()
    return result


def _validate_report_data(stats, include_ai):
    if stats["suppressed"]:
        if include_ai:
            raise BusinessError(422, "反馈覆盖人数不足，无法生成 AI 建议")
        if not stats["items"]:
            raise BusinessError(422, "本周暂无可归档的心理统计")


def generate(db, principal, body):
    from fastapi.encoders import jsonable_encoder

    require_permission(principal, "student-alerts:read")
    ai_stats = None
    ai_summary = None
    ai_fields = ("eligible", "participants", "emotion", "stress")
    if body.include_ai:
        initial = jsonable_encoder(desk_week(db, principal, body.anchor))
        _validate_report_data(initial, True)
        ai_stats = {key: initial[key] for key in ai_fields}
        db.rollback()
        ai_summary = report_ai.suggest("心理周报", ai_stats)

    # Start a fresh transaction so a concurrent request's committed draft is visible.
    db.rollback()
    if not scheduled_repository.lock_employee(db, principal.employee_id):
        raise BusinessError(403, "员工账号不可用")
    stats = jsonable_encoder(desk_week(db, principal, body.anchor))
    _validate_report_data(stats, body.include_ai)
    if ai_stats is not None:
        if ai_stats != {key: stats[key] for key in ai_fields}:
            raise BusinessError(409, "统计数据已更新，请重新生成 AI 建议")
        stats["ai_summary"] = ai_summary
    stats["review_status"] = "draft"
    rid = scheduled_repository.save_wellbeing_draft(
        db, principal.employee_id,
        {"period_start": stats["period_start"], "period_end": stats["period_end"], "scope_version": 1,
         "student_ids": sorted(principal.student_ids), "statistics": stats}, beijing_now(),
    )
    db.commit()
    return {"archive_id": rid, **stats}


def review(db, principal, archive_id, body):
    from sqlalchemy import update
    from .scheduled_repository import generated

    require_permission(principal, "student-alerts:write")
    row = db.execute(select(generated.c.report_content).where(
        generated.c.id == archive_id, generated.c.generated_by == principal.employee_id,
        generated.c.report_type == "psych_weekly", generated.c.status == "completed",
    ).with_for_update()).scalar_one_or_none()
    if not row or row.get("scope_version") != 1 or not set(row.get("student_ids", [])).issubset(principal.student_ids):
        raise BusinessError(404, "周报不存在或已超出权限范围")
    stats = row.get("statistics", {})
    if stats.get("review_status") != "draft":
        raise BusinessError(409, "仅待审核的心理周报可发布")
    stats.update(review_status="published", suggestion=body.suggestion)
    db.execute(update(generated).where(generated.c.id == archive_id).values(report_content=row))
    db.commit()
    return {"id": archive_id, "review_status": "published"}
