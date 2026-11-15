from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from app.core.security.password_policy import UserChosenPassword
from app.shared.types.phone import MobileNumber


class VisitorLogin(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str
    password: str = Field(min_length=1, max_length=128)

    @field_validator("username", mode="before")
    @classmethod
    def normalize_username(cls, value):
        return value.strip().lower() if isinstance(value, str) else value

    @field_validator("username")
    @classmethod
    def validate_username(cls, value):
        if not 3 <= len(value) <= 64 or not value.isascii() or not all(
            char.isalnum() or char in "._-" for char in value
        ):
            raise ValueError("用户名为 3 至 64 个英文字母、数字或 . _ -")
        return value


class VisitorRegister(VisitorLogin):
    username: MobileNumber
    password: UserChosenPassword
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)] | None = None
    contact: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=128)] | None = None


class WebsiteIdentity(BaseModel):
    account_type: Literal["visitor", "student"] = "visitor"


class WebsiteProfile(WebsiteIdentity):
    username: str
    name: str
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


class WebsiteStudentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    class_teacher_id: int = Field(strict=True, ge=1)
    abroad_country: Literal["Singapore", "Germany"]
