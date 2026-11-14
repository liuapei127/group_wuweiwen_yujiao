from datetime import datetime

from sqlalchemy import BigInteger, Integer, String, Text, column, func, or_, select, table, update
from sqlalchemy.orm import Session

from app.modules.student_admin.models import SysUser

from .models import AcademicDeadline, ApplicationProgress


def list_progress(db: Session, student_id: int, before_id: int | None, limit: int) -> list[ApplicationProgress]:
    query = select(ApplicationProgress).where(ApplicationProgress.student_id == student_id)
    if before_id is not None:
        query = query.where(ApplicationProgress.id < before_id)
    return list(db.scalars(query.order_by(ApplicationProgress.id.desc()).limit(limit)))


def lock_progress(db: Session, student_id: int, progress_id: int) -> ApplicationProgress | None:
    query = select(ApplicationProgress).where(
        ApplicationProgress.id == progress_id, ApplicationProgress.student_id == student_id
    ).with_for_update()
    return db.scalar(query)


def list_deadlines(
    db: Session, student_id: int, offset: int, limit: int,
    *, now: datetime, due_by: datetime | None,
) -> list[AcademicDeadline]:
    deadline = AcademicDeadline
    query = select(deadline).where(or_(deadline.student_id == student_id, deadline.student_id.is_(None)))
    if due_by is not None:
        query = query.where(
            deadline.reminder_enabled.is_(True),
            deadline.status.in_(("pending", "reminded")),
            deadline.deadline.between(now, due_by),
        )
    return list(db.scalars(query.order_by(deadline.deadline, deadline.id).offset(offset).limit(limit)))


def complete_personal_deadline(db: Session, student_id: int, deadline_id: int, now: datetime) -> AcademicDeadline | None:
    deadline = AcademicDeadline
    db.execute(update(deadline).where(
        deadline.id == deadline_id, deadline.student_id == student_id,
        deadline.status.in_(("pending", "reminded")),
    ).values(status="done", update_time=now))
    return lock_personal_deadline(db, student_id, deadline_id)


def lock_personal_deadline(db: Session, student_id: int, deadline_id: int) -> AcademicDeadline | None:
    deadline = AcademicDeadline
    return db.scalar(select(deadline).where(
        deadline.id == deadline_id, deadline.student_id == student_id,
    ).with_for_update())


_life_knowledge = table(
    "overseas_life_knowledge", column("id", BigInteger), column("country", String),
    column("category", String), column("title", String), column("content", Text), column("status", Integer),
)


def life_knowledge(db: Session, countries: tuple[str, ...], keyword: str, after_id: int, limit: int):
    rows = _life_knowledge.c
    stmt = select(rows.id, rows.category, rows.title, rows.content).where(
        rows.status == 1, func.lower(func.trim(rows.country)).in_(countries), rows.id > after_id,
    )
    if keyword:
        stmt = stmt.where(or_(rows.title.contains(keyword, autoescape=True), rows.content.contains(keyword, autoescape=True)))
    return db.execute(stmt.order_by(rows.id).limit(limit + 1)).mappings().all()


def lock_due_deadlines(db: Session, now: datetime, due_by: datetime, limit: int = 200) -> list[AcademicDeadline]:
    deadline = AcademicDeadline
    student_is_active = select(SysUser.id).where(
        SysUser.id == deadline.student_id, SysUser.user_type == "student", SysUser.status == "normal",
    ).exists()
    candidates = select(deadline.id).where(
        deadline.student_id.is_not(None), student_is_active,
        deadline.status == "pending", deadline.reminder_enabled.is_(True),
        deadline.deadline.between(now, due_by),
    ).order_by(deadline.deadline, deadline.id).limit(limit)
    ids = list(db.scalars(candidates))
    if not ids:
        return []
    locked = select(deadline).where(
        deadline.id.in_(ids), deadline.status == "pending", deadline.reminder_enabled.is_(True),
        deadline.deadline.between(now, due_by),
    ).order_by(deadline.id).with_for_update(skip_locked=db.get_bind().dialect.name == "mysql")
    return list(db.scalars(locked))
