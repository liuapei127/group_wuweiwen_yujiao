from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.dialects.mysql import BIGINT
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


class CsShortTurn(Base):
    """未登录游客的短期记忆，只跟当前客服会话走，会话过期后不再保留。"""

    __tablename__ = "cs_short_turn"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite").with_variant(BIGINT(unsigned=True), "mysql"),
        primary_key=True, autoincrement=True,
    )
    session_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("cs_website_session.id", ondelete="CASCADE"), index=True,
    )
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(String(240))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class CsVisitorProfile(Base):
    """还没有客户记录时，按本人暂存同一份画像；建档后并入客户画像。"""

    __tablename__ = "cs_visitor_profile"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    visitor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("visitor_account.id", ondelete="CASCADE"), primary_key=True,
    )
    display_name: Mapped[str | None] = mapped_column(String(32))
    destinations: Mapped[str | None] = mapped_column(String(64))
    education: Mapped[str | None] = mapped_column(String(16))
    education_stage: Mapped[str | None] = mapped_column(String(16))
    interests: Mapped[str | None] = mapped_column(String(128))
    attributes: Mapped[dict | None] = mapped_column(JSON)
    summary: Mapped[str] = mapped_column(String(300))
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class CsVisitorMemory(Base):
    """登录游客的长期记忆。账号还在就保留，不随客服会话过期删除。"""

    __tablename__ = "cs_visitor_memory"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite").with_variant(BIGINT(unsigned=True), "mysql"),
        primary_key=True, autoincrement=True,
    )
    visitor_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("visitor_account.id", ondelete="CASCADE"), index=True,
    )
    fact: Mapped[str] = mapped_column(String(200))
    updated_at: Mapped[datetime] = mapped_column(DateTime)
