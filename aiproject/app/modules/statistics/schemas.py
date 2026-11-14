from datetime import date, time

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints


class DailySubmissionCount(BaseModel):
    report_date: date
    submitted_employees: int


class EmployeeReportSummary(BaseModel):
    period_start: date
    period_end: date
    department: str | None
    submitted_employee_days: int
    days: list[DailySubmissionCount]


FormalReportKind = Literal["daily", "weekly"]
SummaryText = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1, max_length=8000)]


class FormalReportSections(BaseModel):
    work_summary: SummaryText
    key_progress_summary: SummaryText
    risk_summary: SummaryText
    next_work_suggestions: SummaryText


class FormalReportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    anchor: date | None = None
    report_kind: FormalReportKind


class FormalEmployeeReport(BaseModel):
    archive_id: int
    report_kind: FormalReportKind
    statistics: EmployeeReportSummary
    sections: FormalReportSections


ScheduleKind = Literal["customer_ops", "daily_summary", "weekly_summary", "psych_weekly", "complaint_weekly"]


class ScheduleWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: ScheduleKind
    run_at: time
    enabled: bool = True
