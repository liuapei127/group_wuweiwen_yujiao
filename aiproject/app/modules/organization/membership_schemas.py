from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, NaiveDatetime


class MembershipWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["active", "inactive"]
    effective_from: NaiveDatetime
    effective_to: NaiveDatetime | None = None
    primary: bool = False


class OrganizationManagerWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")
    manager_id: int | None = Field(strict=True, ge=1)
