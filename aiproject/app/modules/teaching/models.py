from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.modules.classroom.models import identifier


class TeachingCourse(Base):
    __tablename__ = "teaching_course"

    id: Mapped[int] = mapped_column(identifier, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    study_stage: Mapped[str] = mapped_column(String(16))
    institution: Mapped[str | None] = mapped_column(String(128))
    enabled: Mapped[bool] = mapped_column(Boolean)


class ClassCourse(Base):
    __tablename__ = "class_course"

    class_id: Mapped[int] = mapped_column(ForeignKey("project_class.id"), primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("teaching_course.id"), primary_key=True)
