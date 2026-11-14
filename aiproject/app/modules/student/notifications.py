from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.modules.todo.models import notification_log
from app.shared.utils.time_util import now_naive


def save_student_result(
    db: Session, student_id: int, related_type: str, related_id: int,
    event: str, title: str, content: str, *, notification_type: str = "student_result",
) -> None:
    key = f"student-result:{related_type}:{related_id}:{event}"
    if db.scalar(select(notification_log.c.id).where(notification_log.c.dedup_key == key)) is not None:
        return
    db.execute(insert(notification_log).values(
        user_id=student_id, notification_type=notification_type, dedup_key=key,
        related_type=related_type, related_id=related_id, title=title, content=content,
        channel="system", status="sent", create_time=now_naive(),
    ))


def student_results(db: Session, student_id: int, before_id: int | None, limit: int):
    stmt = select(
        notification_log.c.id, notification_log.c.title, notification_log.c.content,
        notification_log.c.related_type, notification_log.c.related_id, notification_log.c.create_time,
    ).where(
        notification_log.c.user_id == student_id,
        notification_log.c.notification_type.in_(("student_result", "academic_due")),
        notification_log.c.channel == "system", notification_log.c.status == "sent",
    )
    if before_id is not None:
        stmt = stmt.where(notification_log.c.id < before_id)
    return [dict(row) for row in db.execute(stmt.order_by(notification_log.c.id.desc()).limit(limit)).mappings()]
