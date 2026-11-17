from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Country = Literal["Singapore", "Germany"]


class ProjectWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    abroad_country: Country


class ClassWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=100)
    teacher_id: int = Field(strict=True, gt=0)
    enabled: bool = True


class ClassCreate(ClassWrite):
    project_id: int = Field(strict=True, gt=0)


class ClassPlacement(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    project_id: int = Field(strict=True, gt=0)
    class_id: int = Field(strict=True, gt=0)


class StudentPlacementWrite(ClassPlacement):
    student_id: int = Field(strict=True, gt=0)
    expected_class_id: int | None = Field(ge=1)
    reason: str = Field(min_length=1, max_length=1000)


class StudentPlacementItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    student_id: int = Field(strict=True, gt=0)
    expected_class_id: int | None = Field(ge=1)


class StudentPlacementBatch(ClassPlacement):
    students: list[StudentPlacementItem] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=1, max_length=1000)
