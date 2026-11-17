from datetime import datetime, timedelta
from secrets import token_hex

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError

from .models import CsShortTurn, CustomerChatSession

SESSION_TTL = timedelta(hours=2)


def chat_session(
    db: Session, session_id: str | None, visitor_id: int | None, now: datetime
) -> CustomerChatSession:
    if session_id:
        row = db.scalar(select(CustomerChatSession).where(
            CustomerChatSession.id == session_id,
            CustomerChatSession.visitor_id == visitor_id,
            CustomerChatSession.expires_at > now,
        ).with_for_update())
        if row is None:
            raise BusinessError(404, "客服会话已失效，请重新开始对话")
        return row
    row = CustomerChatSession(id=token_hex(32), visitor_id=visitor_id, expires_at=now + SESSION_TTL)
    db.add(row)
    db.flush()
    return row


def purge_expired_chat_sessions(db: Session, now: datetime) -> int:
    expired = select(CustomerChatSession.id).where(CustomerChatSession.expires_at <= now)
    try:
        db.execute(delete(CsShortTurn).where(CsShortTurn.session_id.in_(expired)))
    except SQLAlchemyError:
        db.rollback()
    result = db.execute(delete(CustomerChatSession).where(CustomerChatSession.expires_at <= now))
    db.commit()
    return result.rowcount


def remember_dify_conversation(
    db: Session, session_id: str, visitor_id: int | None, now: datetime,
    previous: str | None, conversation_id: str | None,
) -> None:
    row = chat_session(db, session_id, visitor_id, now)
    if row.dify_conversation_id == previous:
        row.dify_conversation_id = conversation_id
    db.commit()
