from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, Integer, String, Text
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
