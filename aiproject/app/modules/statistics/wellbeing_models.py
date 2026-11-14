from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

Id = BigInteger().with_variant(Integer, "sqlite")


class WellbeingConsent(Base):
    __tablename__ = "report_wellbeing_consent"

    student_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    granted: Mapped[bool] = mapped_column(Boolean)
    version: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class WellbeingCheckin(Base):
    __tablename__ = "report_wellbeing_checkin"

    student_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    emotion: Mapped[str] = mapped_column(String(16))
    stress: Mapped[str] = mapped_column(String(16))
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class WellbeingCase(Base):
    __tablename__ = "report_wellbeing_case"
    __table_args__ = (Index("ix_report_care_student_status", "student_id", "status"),)

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    student_id: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(16))
    note: Mapped[str] = mapped_column(Text)
    assigned_to: Mapped[int | None] = mapped_column(BigInteger)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class WellbeingFollowup(Base):
    __tablename__ = "report_wellbeing_followup"
    __table_args__ = (Index("ix_report_care_followup_case", "case_id"),)

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    case_id: Mapped[int] = mapped_column(BigInteger)
    actor_id: Mapped[int] = mapped_column(BigInteger)
    note: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime)


class WellbeingEvent(Base):
    __tablename__ = "report_wellbeing_event"

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    employee_id: Mapped[int] = mapped_column(BigInteger)
    title: Mapped[str] = mapped_column(String(100))
    day: Mapped[date] = mapped_column(Date)
    note: Mapped[str] = mapped_column(Text)


class EmployeeReportConflict(Base):
    __tablename__ = "report_employee_conflict"
    __table_args__ = (Index("ix_report_employee_conflict_week", "employee_id", "week_start"),)

    id: Mapped[int] = mapped_column(Id, primary_key=True)
    employee_id: Mapped[int] = mapped_column(BigInteger)
    week_start: Mapped[date] = mapped_column(Date)
    summary: Mapped[str] = mapped_column(String(512))
    daily_excerpt: Mapped[str] = mapped_column(Text)
    weekly_excerpt: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16))
    verify_note: Mapped[str | None] = mapped_column(Text)
