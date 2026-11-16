from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.core.security.password_policy import UserChosenPassword
from app.shared.types.phone import MobileNumber


class VisitorLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: MobileNumber
    password: str = Field(min_length=1, max_length=128)


class VisitorRegister(VisitorLogin):
    password: UserChosenPassword
    nickname: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)] | None = None
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)] | None = None
    contact: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)] | None = None


class WebsiteIdentity(BaseModel):
    account_type: Literal["visitor", "student"] = "visitor"


class WebsiteProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_version: int | None = Field(default=None, ge=0)

    nickname: str = Field(max_length=64)
    name: str = Field(max_length=64)
    contact: str = Field(max_length=128)


class WebsiteProfile(WebsiteIdentity):
    version: int | None = None
    username: str
    name: str
    nickname: str | None = None
    contact: str
    created_at: datetime
    avatar_url: str | None = None


class VisitorToken(WebsiteIdentity):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class WebsiteStudentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    student_id: int = Field(strict=True, ge=1)
    enabled: bool = Field(strict=True)


class WebsiteAccountOut(BaseModel):
    id: int
    username: str
    name: str
    contact: str
    created_at: datetime
    student_id: int | None
    student_enabled: bool
    crm_lead_id: int | None = None


class WebsiteStudentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_teacher_id: int = Field(strict=True, ge=1)
    abroad_country: Literal["Singapore", "Germany"]
