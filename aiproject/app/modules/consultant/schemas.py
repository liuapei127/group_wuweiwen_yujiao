from typing import Annotated
from uuid import UUID

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


LeadStatus = Literal["new", "contacting", "qualified", "signed", "lost"]
FollowType = Literal["phone", "wechat", "meeting", "email", "other"]


class LeadCreate(BaseModel):
    customer_name: str = Field(..., min_length=1, max_length=64)
    contact_info: str | None = Field(default=None, max_length=128)
    gender: Literal["M", "F", "U"] = "U"
    age: int | None = Field(default=None, ge=0, le=120)
    education_level: str | None = None
    intended_country: str | None = None
    intended_major: str | None = None
    background_info: str | None = None
    source_channel: str | None = None
    owner_employee_id: int | None = Field(default=None, ge=1)
    remark: str | None = None


class LeadUpdate(BaseModel):
    contact_info: str | None = None
    intended_country: str | None = None
    intended_major: str | None = None
    background_info: str | None = None
    remark: str | None = None


class LeadStatusUpdate(BaseModel):
    status: LeadStatus
    lost_reason: str | None = None


class LeadOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_name: str
    contact_info: str | None
    gender: str
    age: int | None
    education_level: str | None
    intended_country: str | None
    intended_major: str | None
    background_info: str | None
    source_channel: str | None
    status: str
    owner_employee_id: int
    last_contact_time: datetime | None
    lost_reason: str | None
    remark: str | None
    create_time: datetime
    update_time: datetime


class LeadListParams(BaseModel):
    keyword: str | None = None
    status: LeadStatus | None = None
    owner_employee_id: int | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class FollowUpCreate(BaseModel):
    employee_id: int | None = Field(default=None, ge=1)
    follow_type: FollowType | None = None
    content: str = Field(..., min_length=1)
    next_plan: str | None = None


class FollowUpOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lead_id: int
    employee_id: int
    follow_type: str | None
    content: str
    next_plan: str | None
    create_time: datetime


class LeadDetailOut(BaseModel):
    lead: LeadOut
    follow_ups: list[FollowUpOut]


class VisitorQueueEntry(BaseModel):
    visitor_id: int
    registered_at: datetime
    nickname: str | None = None


class ClaimedVisitor(VisitorQueueEntry):
    name: str
    contact: str
    claimed_at: datetime
    last_contact_at: datetime | None
    manual_source_id: int | None
    crm_lead_id: int | None = None


class VisitorCallCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: UUID
    notes: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]


class VisitorCallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    advisor_id: int
    notes: str
    recorded_at: datetime


class VisitorReservationOut(BaseModel):
    id: int
    event_id: int
    event_name: str
    start_time: datetime
    end_time: datetime | None
    location: str | None
    event_status: str
    status: str
    reserved_at: datetime
    cancelled_at: datetime | None
    attended_at: datetime | None


class VisitorLeadCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source_id: int = Field(ge=1)
    customer_name: str = Field(min_length=1, max_length=64)
    contact_info: str = Field(min_length=1, max_length=128)
    intended_major: str | None = Field(default=None, max_length=128)
    remark: str = Field(min_length=1, max_length=10000)
