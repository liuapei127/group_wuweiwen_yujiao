from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime, model_validator


class EventCreate(BaseModel):
    """活动起止时间使用北京时间。"""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    event_name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=10000)
    start_time: NaiveDatetime
    end_time: NaiveDatetime
    location: str = Field(min_length=1, max_length=255)
    max_participants: int = Field(ge=1, le=2147483647)

    @model_validator(mode="after")
    def validate_time(self):
        if self.start_time.microsecond or self.end_time.microsecond or self.start_time >= self.end_time:
            raise ValueError("活动时间精确到秒，结束时间必须晚于开始时间")
        return self


class EventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_name: str
    description: str | None
    start_time: datetime
    end_time: datetime | None
    location: str | None
    max_participants: int | None
    current_participants: int


class RegistrationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    status: str
    attended_at: datetime | None
    checked_in_by: int | None


class StaffRegistrationOut(RegistrationOut):
    customer_id: int | None
    customer_name: str | None = None


class VisitorEventOut(EventOut):
    reservation_status: Literal["registered", "cancelled", "attended"] | None = None


class VisitorReservationOut(BaseModel):
    event: EventOut
    reservation: RegistrationOut
