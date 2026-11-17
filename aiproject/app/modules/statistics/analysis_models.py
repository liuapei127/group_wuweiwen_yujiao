from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ReportRules(Base):
    __tablename__ = "report_analysis_rules"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=False)
    version: Mapped[int] = mapped_column(Integer)
    settings: Mapped[dict] = mapped_column(JSON)
    updated_by: Mapped[int] = mapped_column(BigInteger)
    updated_at: Mapped[datetime] = mapped_column(DateTime)


class ReportScheduleOptions(Base):
    __tablename__ = "report_schedule_options"

    schedule_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    include_ai: Mapped[bool] = mapped_column(Boolean, default=False)


class ReportRuleSignal(Base):
    __tablename__ = "report_rule_signal"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), index=True)
    related_id: Mapped[int] = mapped_column(BigInteger)
    rule_version: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime)
