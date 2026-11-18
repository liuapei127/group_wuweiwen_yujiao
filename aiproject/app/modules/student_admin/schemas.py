from datetime import datetime
from typing import Annotated
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime, StringConstraints, model_validator
from uuid import UUID


class StudentLeaveCreate(BaseModel):
    """请假时间使用学校所在地时间（北京时间）。"""

    model_config = ConfigDict(extra="forbid")

    leave_type: Literal["sick", "personal", "emergency"]
    start_time: NaiveDatetime
    end_time: NaiveDatetime
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    attachment_id: UUID | None = None

    @model_validator(mode="after")
    def validate_interval(self):
        if self.start_time.microsecond or self.end_time.microsecond:
            raise ValueError("请假时间最多精确到秒")
        if self.start_time >= self.end_time:
            raise ValueError("请假结束时间必须晚于开始时间")
        return self


class LeaveApprove(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    approver_id: int | None = Field(default=None, ge=1)
    decision: Literal["approved", "rejected"]
    approval_comment: str | None = Field(default=None, max_length=512)

    @model_validator(mode="after")
    def rejection_requires_reason(self):
        if self.decision == "rejected" and not self.approval_comment:
            raise ValueError("拒绝请假必须填写审批意见")
        return self


class LeaveOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    student_id: int
    student_name: str | None = None
    service_type: str
    leave_type: str | None
    start_time: datetime | None
    end_time: datetime | None
    reason: str
    status: str
    approver_id: int | None
    approval_comment: str | None
    approval_time: datetime | None
    attachment_url: str | None = None
    create_time: datetime
    update_time: datetime
