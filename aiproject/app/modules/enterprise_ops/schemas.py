from typing import Any, Literal

from pydantic import BaseModel, Field


class CommandRequest(BaseModel):
    action: Literal["approve_leave_by_name", "update_lead_status_by_name"]
    params: dict[str, Any] = Field(default_factory=dict)


from dataclasses import dataclass


@dataclass(frozen=True)
class CommandResult:
    data: dict
    message: str
