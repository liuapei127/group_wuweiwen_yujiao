from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class LeaveApprove(BaseModel):
    approver_id: int | None = Field(default=None, ge=1)
    decision: Literal["approved", "rejected"]
    approval_comment: str | None = None


class LeaveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    service_type: str
    leave_type: str | None
    start_time: datetime | None
    end_time: datetime | None
    reason: str
    status: str
    approver_id: int | None
    approval_comment: str | None
    approval_time: datetime | None
    create_time: datetime
    update_time: datetime
