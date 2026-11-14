from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime


class ProgressWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    target_school: str = Field(min_length=1, max_length=128)
    target_major: str | None = Field(default=None, max_length=128)
    stage: Literal["document_prep", "submitted", "under_review", "offer_received", "visa_processing", "enrolled"]
    progress_detail: str | None = Field(default=None, max_length=10000)
    deadline: date | None = None
    next_action: str | None = Field(default=None, max_length=255)


class ProgressOut(ProgressWrite):
    model_config = ConfigDict(from_attributes=True)

    id: int
    update_time: datetime


class DeadlineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    deadline_type: str
    description: str | None
    deadline: datetime
    status: str
    shared: bool
    reminder_enabled: bool
    due_soon: bool


class DeadlinePage(BaseModel):
    items: list[DeadlineOut]
    has_more: bool


class DeadlineWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=255)
    deadline_type: Literal["paper", "exam", "application", "visa", "other"]
    description: str | None = Field(default=None, max_length=10000)
    deadline: NaiveDatetime
    reminder_enabled: bool = True
