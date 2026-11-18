from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.profile.schemas import Education, EducationStage, Project
from app.shared.types.phone import MobileNumber


ProfileField = Literal[
    "customer_name", "nickname", "contact_info", "age", "education_level", "education_stage",
    "intended_project", "intended_major",
    "domestic_scope", "family_finance", "further_study", "employment", "admission",
    "overseas_intent", "policy_attention", "immigration", "skill", "german",
    "family_support", "cost_sense", "learning_attitude",
    "gender", "core_demand", "language_ability", "hands_on", "logical_thinking", "tag_weight",
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
    domestic_scope: str | None = Field(default=None, max_length=128)
    family_finance: str | None = Field(default=None, max_length=128)
    further_study: str | None = Field(default=None, max_length=128)
    employment: str | None = Field(default=None, max_length=128)
    admission: str | None = Field(default=None, max_length=128)
    overseas_intent: str | None = Field(default=None, max_length=128)
    policy_attention: str | None = Field(default=None, max_length=128)
    immigration: str | None = Field(default=None, max_length=128)
    skill: str | None = Field(default=None, max_length=128)
    german: str | None = Field(default=None, max_length=128)
    family_support: str | None = Field(default=None, max_length=128)
    cost_sense: str | None = Field(default=None, max_length=128)
    learning_attitude: str | None = Field(default=None, max_length=128)
    gender: str | None = Field(default=None, max_length=128)
    core_demand: str | None = Field(default=None, max_length=128)
    language_ability: str | None = Field(default=None, max_length=1000)
    hands_on: str | None = Field(default=None, max_length=128)
    logical_thinking: str | None = Field(default=None, max_length=128)
    tag_weight: dict[Annotated[str, Field(min_length=1, max_length=64)], Annotated[float, Field(strict=True, ge=0, le=1)]] | None = Field(default=None, max_length=100)


class VersionedProfile(SharedFields):
    expected_version: int = Field(ge=0)


class ScreeningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_version: int = Field(ge=0)


class ImportConfirm(ScreeningRequest):
    preview_id: UUID
    fields: list[ProfileField] = Field(min_length=1, max_length=27)
    source_id: int | None = Field(default=None, ge=1)
    ownership_confirmed: bool = Field(default=False, strict=True)


class VerifiedIdentity(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=64)
    mobile: MobileNumber
    confirmed: Literal[True]
