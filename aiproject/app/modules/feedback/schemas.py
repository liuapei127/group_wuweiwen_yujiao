from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class TicketUpdate(Input):
    expected_status: Literal["pending","processing","resolved","closed"]
    status: Literal["processing","resolved","closed"]
    solution: str | None = Field(default=None,max_length=10000)


class TicketRouting(Input):
    expected_status: Literal["pending", "processing"]
    expected_category: str | None
    expected_assignee_id: int | None = Field(ge=1)
    category: Literal["learning", "company"]
    reason: str = Field(min_length=1, max_length=2000)


class StudentComplaintCreate(Input):
    category: Literal["learning", "company"]
    title: str | None = Field(default=None, max_length=255)
    content: str = Field(min_length=1, max_length=10000)
    ticket_type: Literal["complaint", "suggestion"] = "complaint"


class StudentComplaintOut(BaseModel):
    id: int
    category: str | None
    title: str | None
    content: str
    status: str
    solution: str | None
    assignee_id: int | None = None
    create_time: datetime
    update_time: datetime
