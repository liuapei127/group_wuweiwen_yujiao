from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CustomerChatSession(Base):
    __tablename__ = "cs_website_session"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    visitor_id: Mapped[int | None] = mapped_column(ForeignKey("visitor_account.id", ondelete="CASCADE"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    dify_conversation_id: Mapped[str | None] = mapped_column(String(64))
    previous_query: Mapped[str | None] = mapped_column(String(1200))
    event_options: Mapped[list[dict] | None] = mapped_column(JSON)
    pending_event_id: Mapped[int | None] = mapped_column(BigInteger)
