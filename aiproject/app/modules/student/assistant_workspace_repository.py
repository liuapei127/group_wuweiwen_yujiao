"""Owned workspace reads and task locks. Transaction boundaries belong to services."""
from sqlalchemy import func, select

from app.modules.auth.models import accounts
from .models import ApplicationProgress, StudentAssistantConversation, StudentAssistantTask


def conversation(db, student_id, conversation_id, *, lock=False):
    query = select(StudentAssistantConversation).where(
        StudentAssistantConversation.id == conversation_id,
        StudentAssistantConversation.student_id == student_id,
    )
    return db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)


def latest_task(db, student_id, conversation_id, *, active=False, lock=False):
    query = select(StudentAssistantTask).where(
        StudentAssistantTask.student_id == student_id,
        StudentAssistantTask.conversation_id == conversation_id,
    )
    if active:
        query = query.where(StudentAssistantTask.status.in_(("collecting", "awaiting_confirmation")))
    query = query.order_by(StudentAssistantTask.ordinal.desc()).limit(1)
    return db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)


def task(db, student_id, task_id, *, lock=False):
    query = select(StudentAssistantTask).where(
        StudentAssistantTask.id == task_id, StudentAssistantTask.student_id == student_id,
    )
    return db.scalar(query.with_for_update().execution_options(populate_existing=True) if lock else query)


def applications(db, student_id, limit=10):
    handler = accounts.alias("application_handler")
    query = select(
        ApplicationProgress, handler.c.real_name.label("handler_name"),
    ).outerjoin(handler, handler.c.id == ApplicationProgress.handler_id).where(
        ApplicationProgress.student_id == student_id,
    ).order_by(ApplicationProgress.update_time.desc(), ApplicationProgress.id.desc()).limit(limit)
    return db.execute(query).all()


def next_ordinal(db, student_id, conversation_id):
    return 1 + (db.scalar(select(func.max(StudentAssistantTask.ordinal)).where(
        StudentAssistantTask.student_id == student_id,
        StudentAssistantTask.conversation_id == conversation_id,
    )) or 0)
