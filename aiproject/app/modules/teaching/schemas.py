from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CourseWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=128)
    study_stage: Literal["preparatory", "language", "overseas"]
    institution: str | None = Field(default=None, max_length=128)
    enabled: bool = True


class ClassCoursesWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    course_ids: list[int] = Field(max_length=200)
