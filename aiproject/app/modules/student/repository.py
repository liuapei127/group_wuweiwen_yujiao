from datetime import datetime

from sqlalchemy import BigInteger, Date, DateTime, JSON, Integer, String, Text, column, func, or_, select, table, update
from sqlalchemy.orm import Session

from app.modules.student_admin.models import SysUser
from app.modules.student_admin.models import StudentAdminService
from app.modules.auth.models import accounts
from app.modules.auth.repository import student_info
from app.modules.feedback.models import student_feedback_ticket
from app.modules.classroom.models import ClassEnrollment, ProjectClass
from app.modules.visitor.catalog import _courses

from .models import AcademicDeadline, ApplicationProgress


def academic_profile(db: Session, student_id: int):
    teacher = accounts.alias("class_teacher")
    stmt = select(
        accounts.c.real_name.label("student_name"), student_info.c.student_no,
        student_info.c.school, student_info.c.major, student_info.c.abroad_country,
        teacher.c.real_name.label("class_teacher"),
        ProjectClass.id.label("class_id"), ProjectClass.name.label("class_name"),
        ProjectClass.project_id, _courses.c.project_name,
    ).select_from(
        accounts.outerjoin(student_info, student_info.c.user_id == accounts.c.id)
        .outerjoin(teacher, (teacher.c.id == student_info.c.class_teacher_id)
                   & (teacher.c.status == "normal"))
        .outerjoin(ClassEnrollment, ClassEnrollment.student_id == accounts.c.id)
        .outerjoin(ProjectClass, ProjectClass.id == ClassEnrollment.class_id)
        .outerjoin(_courses, _courses.c.id == ProjectClass.project_id)
    ).where(accounts.c.id == student_id, accounts.c.user_type == "student", accounts.c.status == "normal")
    return db.execute(stmt).mappings().one_or_none()


def notification_sources(db: Session, student_id: int, notices: list[dict]) -> dict:
    """Batch-load only sources the current student may read, including old notices."""
    found = {}
    for source_type, source, ownership, columns in (
        ("student_admin_service", StudentAdminService.__table__,
         StudentAdminService.student_id == student_id,
         ("id", "leave_type", "start_time", "end_time", "reason", "status", "approval_comment", "approval_time")),
        ("student_feedback_ticket", student_feedback_ticket,
         student_feedback_ticket.c.student_id == student_id,
         ("id", "title", "content", "category", "status", "solution", "create_time")),
        ("academic_deadline", AcademicDeadline.__table__,
         or_(AcademicDeadline.student_id == student_id, AcademicDeadline.student_id.is_(None)),
         ("id", "title", "description", "deadline_type", "deadline", "status")),
    ):
        ids = {row["related_id"] for row in notices if row["related_type"] == source_type}
        if not ids:
            continue
        stmt = select(*(source.c[name] for name in columns)).where(source.c.id.in_(ids), ownership)
        for row in db.execute(stmt).mappings():
            found[(source_type, row["id"])] = dict(row)
    return found


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
    column("city", String), column("source_title", String), column("source_url", String),
    column("verified_at", Date), column("update_time", DateTime), column("details", JSON),
)


def life_knowledge(db: Session, countries: tuple[str, ...], keyword: str, after_id: int, limit: int, *, category: str = "", extended: bool = False):
    rows = _life_knowledge.c
    fields = [rows.id, rows.category, rows.title, rows.content]
    if extended:
        fields += [rows.country, rows.city, rows.source_title, rows.source_url, rows.verified_at, rows.update_time, rows.details]
    stmt = select(*fields).where(
        rows.status == 1, func.lower(func.trim(rows.country)).in_(countries), rows.id > after_id,
    )
    if category:
        stmt = stmt.where(rows.category == category)
    if keyword:
        stmt = stmt.where(or_(rows.title.contains(keyword, autoescape=True), rows.content.contains(keyword, autoescape=True)))
    return db.execute(stmt.order_by(rows.id).limit(limit + 1)).mappings().all()


def iter_life_knowledge(db: Session, countries: tuple[str, ...], after_id: int = 0, *, category: str = ""):
    """Read every matching article in bounded batches, including older catalogues."""
    cursor = after_id
    while True:
        rows = life_knowledge(db, countries, "", cursor, 50, category=category, extended=True)
        yield from rows[:50]
        if len(rows) <= 50:
            return
        cursor = rows[49]["id"]


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
