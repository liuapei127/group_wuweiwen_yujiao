from datetime import datetime, timedelta, timezone
import hashlib
import json

from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.security import EmployeePrincipal
from app.core.security.authorization import require_permission, require_student_scope
from app.modules.auth.repository import AuthRepository
from app.modules.student_admin.repository import StudentAdminRepository
from app.shared.constants.study_policies import StudentPolicies, destination_labels, study_policies
from app.shared.utils.time_util import now_naive
from app.modules.visitor.repository import student_destination

from . import notifications, repository
from .models import AcademicClassBatch, AcademicDeadline, ApplicationProgress
from .schemas import DeadlineOut, DeadlinePage, DeadlineWrite, ProgressOut, ProgressWrite


def academic_profile(db: Session, student_id: int) -> dict:
    row = repository.academic_profile(db, student_id)
    if row is None:
        raise BusinessError(404, "学生学籍不可用，请联系老师核对")
    return dict(row)

def student_policies(db: Session, student_id: int) -> StudentPolicies:
    return study_policies(student_destination(db, student_id))


def application_progress(db: Session, student_id: int, before_id: int | None, limit: int) -> list[ProgressOut]:
    return [ProgressOut.model_validate(row) for row in repository.list_progress(db, student_id, before_id, limit)]


def scoped_students(db: Session, principal: EmployeePrincipal, permission: str):
    require_permission(principal, permission)
    return [
        {"id": row["id"], "real_name": row["real_name"], "student_no": row["student_no"]}
        for row in AuthRepository(db).students(principal.student_ids)
    ]


def staff_progress(
    db: Session, principal: EmployeePrincipal, student_id: int, before_id: int | None, limit: int,
) -> list[ProgressOut]:
    require_student_scope(principal, student_id, "applications:read")
    return application_progress(db, student_id, before_id, limit)


def save_progress(
    db: Session, principal: EmployeePrincipal, student_id: int, payload: ProgressWrite,
    progress_id: int | None = None,
) -> ProgressOut:
    require_student_scope(principal, student_id, "applications:write")
    try:
        if not StudentAdminRepository(db).lock_student(student_id):
            raise BusinessError(404, "学生档案不存在或已停用")
        now = now_naive()
        fields = payload.model_dump()
        if progress_id is None:
            row = ApplicationProgress(
                student_id=student_id, handler_id=principal.employee_id, create_time=now, update_time=now, **fields,
            )
            db.add(row)
        else:
            row = repository.lock_progress(db, student_id, progress_id)
            if row is None:
                raise BusinessError(404, "申请记录不存在")
            for field, value in fields.items():
                setattr(row, field, value)
            row.update_time = now
        db.flush()
        result = ProgressOut.model_validate(row)
        AuthRepository(db).audit(principal.employee_id, "application_progress_saved", row.id, {
            "student_id": student_id, **payload.model_dump(mode="json"),
        })
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


# The legacy deadline column stores wall-clock Beijing time.
_BEIJING = timezone(timedelta(hours=8))
_REMINDER_WINDOW = timedelta(days=7)


def _deadline_now() -> datetime:
    return datetime.now(_BEIJING).replace(tzinfo=None, microsecond=0)


def academic_deadlines(
    db: Session, student_id: int, *, offset: int, limit: int, upcoming: bool,
) -> DeadlinePage:
    now = _deadline_now()
    due_by = now + _REMINDER_WINDOW
    rows = repository.list_deadlines(
        db, student_id, offset, limit + 1, now=now, due_by=due_by if upcoming else None,
    )
    return DeadlinePage(items=[_deadline_view(row, now) for row in rows[:limit]], has_more=len(rows) > limit)


def finish_deadline(db: Session, student_id: int, deadline_id: int) -> DeadlineOut:
    now = _deadline_now()
    try:
        row = repository.complete_personal_deadline(db, student_id, deadline_id, now)
        if row is None:
            raise BusinessError(404, "个人考务记录不存在")
        if row.status != "done":
            raise BusinessError(409, "当前考务状态无法标记完成")
        result = _deadline_view(row, now)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


def _deadline_view(row: AcademicDeadline, now: datetime) -> DeadlineOut:
    return DeadlineOut(
        id=row.id, title=row.title, deadline_type=row.deadline_type, description=row.description,
        study_stage=row.study_stage,
        deadline=row.deadline, status=row.status, shared=row.student_id is None, reminder_enabled=row.reminder_enabled,
        due_soon=(row.reminder_enabled and row.status in ("pending", "reminded")
                  and now <= row.deadline <= now + _REMINDER_WINDOW),
    )


def staff_deadlines(db: Session, principal: EmployeePrincipal, student_id: int, offset: int, limit: int) -> DeadlinePage:
    require_student_scope(principal, student_id, "academics:read")
    return academic_deadlines(db, student_id, offset=offset, limit=limit, upcoming=False)


def save_deadline(
    db: Session, principal: EmployeePrincipal, student_id: int, payload: DeadlineWrite,
    deadline_id: int | None = None,
) -> DeadlineOut:
    require_student_scope(principal, student_id, "academics:write")
    try:
        if not StudentAdminRepository(db).lock_student(student_id):
            raise BusinessError(404, "学生档案不存在或已停用")
        now = _deadline_now()
        fields = payload.model_dump()
        if deadline_id is None:
            row = AcademicDeadline(student_id=student_id, create_time=now, update_time=now, **fields)
            db.add(row)
        else:
            row = repository.lock_personal_deadline(db, student_id, deadline_id)
            if row is None:
                raise BusinessError(404, "个人考务记录不存在")
            if row.status not in ("pending", "reminded"):
                raise BusinessError(409, "当前考务状态无法更正")
            if row.deadline != payload.deadline:
                row.status = "pending"
            for field, value in fields.items():
                setattr(row, field, value)
            row.update_time = now
        db.flush()
        result = _deadline_view(row, now)
        AuthRepository(db).audit(principal.employee_id, "academic_deadline_saved", row.id, {
            "student_id": student_id, **payload.model_dump(mode="json"),
        })
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


def overseas_resources(db: Session, student_id: int, keyword: str, after_id: int, limit: int, *, category: str = "", country: str = ""):
    from app.core.config import get_settings
    if category and category not in {"arrival", "medical", "transport", "housing", "study", "emergency", "daily_life", "other"}:
        raise BusinessError(422, "未知生活资料类别")
    if country and country not in {"Germany", "Singapore"}:
        raise BusinessError(422, "未知资料地区")
    country = country or student_policies(db, student_id).country
    if country is None:
        return {"items": [], "next_after_id": None}
    labels = destination_labels(country)
    extended = get_settings().stu_assistant_mode == "workspace"
    if keyword and extended:
        from .assistant_knowledge import article_matches
        found = []
        for row in repository.iter_life_knowledge(db, labels, after_id, category=category):
            if article_matches(row, keyword):
                found.append(row)
                if len(found) > limit:
                    break
    else:
        found = repository.life_knowledge(db, labels, keyword, after_id, limit, category=category, extended=extended)
    return {"items": [dict(row) for row in found[:limit]],
            "next_after_id": found[limit - 1]["id"] if len(found) > limit else None}


def class_deadlines(db, principal, class_id, payload):
    from app.modules.classroom import repository as classrooms

    require_permission(principal, "academics:write")
    fingerprint = hashlib.sha256(json.dumps(
        payload.model_dump(mode="json", exclude={"request_id"}), sort_keys=True, ensure_ascii=False,
    ).encode()).hexdigest()
    try:
        classroom = classrooms.classroom(db, class_id, lock=True)
        if classroom is None or classroom.teacher_id != principal.employee_id:
            raise BusinessError(404, "班级不存在或无权操作")
        previous = db.get(AcademicClassBatch, str(payload.request_id), with_for_update=True)
        if previous:
            if previous.actor_id != principal.employee_id or previous.class_id != class_id or previous.payload_hash != fingerprint:
                raise BusinessError(409, "这次发布标识已用于其他内容，请重新核对")
            return {"id": previous.id, "student_count": previous.student_count, "replayed": True}
        student_ids = classrooms.class_students(db, class_id)
        if not student_ids:
            raise BusinessError(422, "班级暂无学生")
        if not set(student_ids) <= principal.student_ids:
            raise BusinessError(403, "班级学生范围已变化，请刷新后重试")
        fields = payload.model_dump(exclude={"request_id"})
        now = _deadline_now()
        for student_id in student_ids:
            if not StudentAdminRepository(db).lock_student(student_id):
                raise BusinessError(409, "班级内有已停用学生，请先核对学生状态")
            db.add(AcademicDeadline(student_id=student_id, create_time=now, update_time=now, **fields))
        batch = AcademicClassBatch(
            id=str(payload.request_id), class_id=class_id, actor_id=principal.employee_id,
            payload_hash=fingerprint, student_count=len(student_ids), created_at=now,
        )
        db.add(batch)
        AuthRepository(db).audit(principal.employee_id, "class_deadlines_published", class_id, {
            "request_id": batch.id, "student_ids": student_ids, "title": payload.title,
        })
        db.commit()
        return {"id": batch.id, "student_count": batch.student_count, "replayed": False}
    except Exception:
        db.rollback()
        raise


def scan_academic_reminders(db: Session) -> int:
    now = _deadline_now()
    try:
        due = repository.lock_due_deadlines(db, now, now + _REMINDER_WINDOW)
        for row in due:
            notifications.save_student_result(
                db, row.student_id, "academic_deadline", row.id, row.deadline.isoformat(),
                "考务即将截止", f"{row.title}，截止时间 {row.deadline:%Y-%m-%d %H:%M}（北京时间）",
                notification_type="academic_due",
            )
            row.status = "reminded"
            row.update_time = now
        db.commit()
        return len(due)
    except Exception:
        db.rollback()
        raise
