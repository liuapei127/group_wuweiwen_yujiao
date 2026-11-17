from datetime import date, datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime, StringConstraints
from uuid import UUID
from app.shared.types.study_stage import StudyStage


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
    study_stage: StudyStage = "unspecified"
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
    study_stage: StudyStage = "unspecified"
    description: str | None = Field(default=None, max_length=10000)
    deadline: NaiveDatetime
    reminder_enabled: bool = True


class DeadlineBatch(DeadlineWrite):
    request_id: UUID


class AssistantTurn(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    role: Literal["user", "assistant"]
    content: Annotated[str, StringConstraints(min_length=1, max_length=4000)]


class StudentAssistantRequest(BaseModel):
    """Website chat turn. Prefer ``conversation_id``; server loads short history + mem0."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    query: Annotated[str, StringConstraints(min_length=1, max_length=4000)]
    conversation_id: Annotated[str, StringConstraints(min_length=8, max_length=64)] | None = None
    history: list[AssistantTurn] | None = Field(default=None, max_length=12)
    mock_country: Literal["Germany", "Singapore"] | None = None


class StudentAssistantConversationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: Annotated[str, StringConstraints(min_length=1, max_length=128)] | None = None
