from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.profile.schemas import Education, EducationStage, Project
from app.shared.types.phone import MobileNumber


ProfileField = Literal[
    "customer_name", "nickname", "contact_info", "age", "education_level", "education_stage",
    "intended_project", "intended_major",
]


class SharedFields(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    customer_name: str | None = Field(default=None, max_length=64)
    nickname: str | None = Field(default=None, max_length=64)
    contact_info: str | None = Field(default=None, max_length=128)
    age: int | None = Field(default=None, strict=True, ge=0, le=120)
    education_level: Education | None = None
    education_stage: EducationStage | None = None
    intended_project: Project | None = None
    intended_major: str | None = Field(default=None, max_length=128)


class VersionedProfile(SharedFields):
    expected_version: int = Field(ge=0)


class ScreeningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)


class ImportConfirm(ScreeningRequest):
    preview_id: UUID
    fields: list[ProfileField] = Field(min_length=1, max_length=8)
    source_id: int | None = Field(default=None, ge=1)


class VerifiedIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=64)
    mobile: MobileNumber
    confirmed: Literal[True]
