from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Enum, Integer, String, Text
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

APPLICATION_STAGES = (
    "document_prep", "submitted", "under_review", "offer_received", "visa_processing", "enrolled",
)


class ApplicationProgress(Base):
    __tablename__ = "application_progress"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite").with_variant(BIGINT(unsigned=True), "mysql"),
                                    primary_key=True)
    student_id: Mapped[int] = mapped_column(BigInteger().with_variant(BIGINT(unsigned=True), "mysql"),
                                            index=True)
    target_school: Mapped[str] = mapped_column(String(128))
    target_major: Mapped[str | None] = mapped_column(String(128))
    stage: Mapped[str] = mapped_column(Enum(*APPLICATION_STAGES))
    progress_detail: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[date | None] = mapped_column(Date)
    next_action: Mapped[str | None] = mapped_column(String(255))
    handler_id: Mapped[int | None] = mapped_column(BigInteger().with_variant(BIGINT(unsigned=True), "mysql"))
    create_time: Mapped[datetime] = mapped_column(DateTime)
    update_time: Mapped[datetime] = mapped_column(DateTime)


class AcademicDeadline(Base):
    __tablename__ = "academic_deadline"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite").with_variant(BIGINT(unsigned=True), "mysql"),
                                    primary_key=True)
    student_id: Mapped[int | None] = mapped_column(BigInteger().with_variant(BIGINT(unsigned=True), "mysql"))
    deadline_type: Mapped[str] = mapped_column(Enum("paper", "exam", "application", "visa", "other"))
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    deadline: Mapped[datetime] = mapped_column(DateTime)
    reminder_enabled: Mapped[bool] = mapped_column(default=True)
    status: Mapped[str] = mapped_column(Enum("pending", "reminded", "done", "missed"), default="pending")
    create_time: Mapped[datetime] = mapped_column(DateTime)
    update_time: Mapped[datetime] = mapped_column(DateTime)


class StudentAssistantConversation(Base):
    """One website assistant thread per student. Titles are generated locally."""

    __tablename__ = "stu_assistant_conversation"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    student_id: Mapped[int] = mapped_column(
        BigInteger().with_variant(BIGINT(unsigned=True), "mysql"), index=True
    )
    title: Mapped[str] = mapped_column(String(128), default="新对话")
    create_time: Mapped[datetime] = mapped_column(DateTime)
    update_time: Mapped[datetime] = mapped_column(DateTime, index=True)


class StudentAssistantMessage(Base):
    """Short-term turns of a conversation, read back as prompt history."""

    __tablename__ = "stu_assistant_message"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite").with_variant(BIGINT(unsigned=True), "mysql"),
        primary_key=True,
        autoincrement=True,
    )
    conversation_id: Mapped[str] = mapped_column(String(36), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    create_time: Mapped[datetime] = mapped_column(DateTime)


class StuMem0Memory(Base):
    """Local mem0-shaped long-term memory, isolated per website account."""

    __tablename__ = "stu_mem0_memory"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite").with_variant(BIGINT(unsigned=True), "mysql"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    memory: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[str | None] = mapped_column(Text)
    create_time: Mapped[datetime] = mapped_column(DateTime)
    update_time: Mapped[datetime] = mapped_column(DateTime)
