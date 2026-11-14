from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, Enum, JSON, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EmployeeDailyReport(Base):
    __tablename__ = "employee_daily_report"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    employee_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    report_date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_content: Mapped[str | None] = mapped_column(Text)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    key_progress: Mapped[dict | list | None] = mapped_column(JSON)
    risks: Mapped[dict | list | None] = mapped_column(JSON)
    next_plan: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Enum("draft", "submitted"), default="submitted", nullable=False)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class WeeklySubmission(Base):
    __tablename__ = "employee_weekly_submission"

    employee_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    week_start: Mapped[date] = mapped_column(Date, primary_key=True)
    content: Mapped[str] = mapped_column(Text)
    key_progress: Mapped[str | None] = mapped_column(Text)
    risks: Mapped[str | None] = mapped_column(Text)
    next_plan: Mapped[str | None] = mapped_column(Text)
    submitted_at: Mapped[datetime] = mapped_column(DateTime)
