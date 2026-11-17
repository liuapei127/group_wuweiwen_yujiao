from datetime import datetime
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.mysql import BIGINT
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

identifier = BigInteger().with_variant(BIGINT(unsigned=True), "mysql").with_variant(Integer, "sqlite")


class TeachingProject(Base):
    __tablename__ = "teaching_project"

    project_id: Mapped[int] = mapped_column(identifier, primary_key=True, autoincrement=False)
    abroad_country: Mapped[str] = mapped_column(String(16))


class ProjectClass(Base):
    __tablename__ = "project_class"
    __table_args__ = (UniqueConstraint("project_id", "name", name="uq_project_class_name"),)

    id: Mapped[int] = mapped_column(identifier, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("teaching_project.project_id"))
    teacher_id: Mapped[int] = mapped_column(identifier, index=True)
    name: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean)


class ClassEnrollment(Base):
    __tablename__ = "student_class_enrollment"

    student_id: Mapped[int] = mapped_column(identifier, primary_key=True, autoincrement=False)
    class_id: Mapped[int] = mapped_column(ForeignKey("project_class.id"), index=True)


class ClassPlacementHistory(Base):
    __tablename__ = "class_placement_history"

    id: Mapped[int] = mapped_column(identifier, primary_key=True)
    student_id: Mapped[int] = mapped_column(identifier, index=True)
    from_class_id: Mapped[int | None] = mapped_column(identifier)
    to_class_id: Mapped[int] = mapped_column(identifier)
    actor_id: Mapped[int] = mapped_column(identifier)
    reason: Mapped[str] = mapped_column(String(1000))
    changed_at: Mapped[datetime] = mapped_column(DateTime)
