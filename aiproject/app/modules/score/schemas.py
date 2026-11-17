from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict, model_validator
from app.shared.types.study_stage import StudyStage

class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class ScoreInput(Input):
    student_id: int = Field(gt=0)
    course_name: str = Field(default="", max_length=128)
    course_id: int | None = Field(default=None, strict=True, gt=0)
    study_stage: StudyStage = "unspecified"
    score: Decimal = Field(ge=0,le=999.99,max_digits=5,decimal_places=2)
    semester: str | None = Field(default=None,max_length=32)
    credit: Decimal | None = Field(default=None,ge=0,le=99.9,max_digits=3,decimal_places=1)

    @model_validator(mode="after")
    def course_required(self):
        if not self.course_id and not self.course_name:
            raise ValueError("请选择课程")
        return self


class ScoreCreate(ScoreInput):
    exam_key: str | None = Field(default=None, min_length=1, max_length=96)
    submission_key: str | None = Field(default=None, min_length=1, max_length=96)


class ScoreCorrection(ScoreInput):
    expected_version: int | None = Field(default=None, ge=1)
    correction_reason: str | None = Field(default=None, min_length=1, max_length=2000)
