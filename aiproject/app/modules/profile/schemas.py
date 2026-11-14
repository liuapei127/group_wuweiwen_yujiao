from datetime import datetime
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Project(StrEnum):
    SG_JUNIOR = "sg_junior"
    SG_SENIOR = "sg_senior"
    SG_HOSPITALITY = "sg_hospitality"
    SG_AVIATION = "sg_aviation"
    SG_TOP_UP = "sg_top_up"
    SG_MASTERS = "sg_masters"
    DE_VOCATIONAL = "de_vocational"


class Education(StrEnum):
    JUNIOR = "junior_secondary"
    SENIOR = "senior_secondary"
    VOCATIONAL = "vocational_secondary"
    COLLEGE = "college"
    BACHELOR = "bachelor"
    POSTGRADUATE = "postgraduate"
    OTHER = "other"


class EducationStage(StrEnum):
    ENROLLED = "enrolled"
    SENIOR_YEAR_TWO = "senior_year_two"
    GRADUATED = "graduated"


class ScreeningInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: Project | None = None
    age: int | None = Field(default=None, strict=True, ge=0)
    education: Education | None = None
    education_stage: EducationStage | None = None


class ScreeningStatus(StrEnum):
    NEEDS_INFORMATION = "needs_information"
    NEEDS_REVIEW = "needs_review"
    POTENTIAL_MATCH = "potential_match"
    NOT_MATCHED = "not_matched"


class ScreeningResult(BaseModel):
    project: Project | None
    status: ScreeningStatus
    missing_fields: tuple[str, ...] = ()
    findings: tuple[str, ...] = ()


class VisitorMaterialProgress(BaseModel):
    source_id: int
    file_name: str | None
    submitted_at: datetime
    status: Literal["received", "needs_information", "reviewed"]
