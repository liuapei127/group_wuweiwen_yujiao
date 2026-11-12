from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DailyReportCreate(BaseModel):
    employee_id: int | None = Field(default=None, ge=1)
    report_date: date | None = None
    raw_content: str | None = None
    content: str = Field(..., min_length=1)
    key_progress: list[str] | dict[str, Any] | None = None
    risks: list[str] | dict[str, Any] | None = None
    next_plan: str | None = None


class DailyReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    employee_id: int
    report_date: date
    content: str
    key_progress: Any
    risks: Any
    next_plan: str | None
    status: str
    create_time: datetime
