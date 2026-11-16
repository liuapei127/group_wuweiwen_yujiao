from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CrmLead(Base):
    __tablename__ = "crm_lead"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    customer_name: Mapped[str] = mapped_column(String(64), nullable=False)
    contact_info: Mapped[str | None] = mapped_column(String(128))
    gender: Mapped[str] = mapped_column(Enum("M", "F", "U"), default="U")
    age: Mapped[int | None] = mapped_column(Integer)
    education_level: Mapped[str | None] = mapped_column(String(64))
    intended_country: Mapped[str | None] = mapped_column(String(128))
    intended_major: Mapped[str | None] = mapped_column(String(128))
    intended_project: Mapped[str | None] = mapped_column(String(40))
    education_stage: Mapped[str | None] = mapped_column(String(24))
    profile_version: Mapped[int] = mapped_column(Integer, default=0, server_default=text("0"))
    background_info: Mapped[str | None] = mapped_column(Text)
    customer_profile_id: Mapped[int | None] = mapped_column(BigInteger)
    source_channel: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        Enum("new", "contacting", "qualified", "signed", "lost"),
        default="new",
        nullable=False,
    )
    owner_employee_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    last_contact_time: Mapped[datetime | None] = mapped_column(DateTime)
    lost_reason: Mapped[str | None] = mapped_column(String(255))
    remark: Mapped[str | None] = mapped_column(Text)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class CrmFollowUp(Base):
    __tablename__ = "crm_follow_up"

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    employee_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    follow_type: Mapped[str | None] = mapped_column(Enum("phone", "wechat", "meeting", "email", "other"))
    content: Mapped[str] = mapped_column(Text, nullable=False)
    next_plan: Mapped[str | None] = mapped_column(String(255))
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class VisitorIntake(Base):
    __tablename__ = "visitor_intake"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    visitor_id: Mapped[int] = mapped_column(ForeignKey("visitor_account.id"), primary_key=True, autoincrement=False)
    advisor_id: Mapped[int] = mapped_column(BigInteger, index=True)
    claimed_at: Mapped[datetime] = mapped_column(DateTime)
    last_contact_at: Mapped[datetime | None] = mapped_column(DateTime)
    manual_source_id: Mapped[int | None] = mapped_column(ForeignKey("customer_source.id"), unique=True)
    crm_lead_id: Mapped[int | None] = mapped_column(ForeignKey("crm_lead.id"), unique=True)


class VisitorCall(Base):
    __tablename__ = "visitor_call"
    __table_args__ = (
        UniqueConstraint("visitor_id", "request_id", name="uq_visitor_call_request"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    visitor_id: Mapped[int] = mapped_column(ForeignKey("visitor_intake.visitor_id"))
    advisor_id: Mapped[int] = mapped_column(BigInteger)
    request_id: Mapped[str] = mapped_column(String(36))
    notes: Mapped[str] = mapped_column(Text)
    recorded_at: Mapped[datetime] = mapped_column(DateTime)
