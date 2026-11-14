from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EventLecture(Base):
    __tablename__ = "event_lecture"
    __table_args__ = (
        CheckConstraint("max_participants > 0", name="ck_event_capacity_positive"),
        CheckConstraint("current_participants BETWEEN 0 AND max_participants", name="ck_event_capacity_used"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite").with_variant(BIGINT(unsigned=True), "mysql"), primary_key=True)
    event_type: Mapped[str] = mapped_column(Enum("online", "offline", "hybrid"), default="offline")
    status: Mapped[str] = mapped_column(Enum("upcoming", "ongoing", "ended", "cancelled"), default="upcoming")
    event_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    start_time: Mapped[datetime] = mapped_column(DateTime)
    end_time: Mapped[datetime | None] = mapped_column(DateTime)
    location: Mapped[str | None] = mapped_column(String(255))
    max_participants: Mapped[int | None] = mapped_column(Integer)
    current_participants: Mapped[int] = mapped_column(Integer, default=0)
    organizer_id: Mapped[int | None] = mapped_column(BigInteger)
    create_time: Mapped[datetime] = mapped_column(DateTime)


class EventRegistration(Base):
    __tablename__ = "event_registration"
    __table_args__ = (
        UniqueConstraint("event_id", "customer_id", name="uq_event_customer"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    event_id: Mapped[int] = mapped_column(ForeignKey("event_lecture.id"))
    customer_id: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(Enum("registered", "cancelled", "attended", "no_show", name="event_booking_status"))
    create_time: Mapped[datetime] = mapped_column(DateTime)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime)
    attended_at: Mapped[datetime | None] = mapped_column(DateTime)
    checked_in_by: Mapped[int | None] = mapped_column(BigInteger)
