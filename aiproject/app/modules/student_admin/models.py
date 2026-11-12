from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Enum, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StudentAdminService(Base):
    __tablename__ = "student_admin_service"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    service_type: Mapped[str] = mapped_column(Enum("leave", "exam_query", "other"), nullable=False)
    leave_type: Mapped[str | None] = mapped_column(Enum("sick", "personal", "emergency"))
    start_time: Mapped[datetime | None] = mapped_column(DateTime)
    end_time: Mapped[datetime | None] = mapped_column(DateTime)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    attachment_url: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[str] = mapped_column(
        Enum("pending", "approved", "rejected", "cancelled"),
        default="pending",
        nullable=False,
    )
    approver_id: Mapped[int | None] = mapped_column(BigInteger)
    approval_comment: Mapped[str | None] = mapped_column(String(512))
    approval_time: Mapped[datetime | None] = mapped_column(DateTime)
    related_academic_id: Mapped[int | None] = mapped_column(BigInteger)
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)


class SysUser(Base):
    __tablename__ = "sys_user"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    real_name: Mapped[str] = mapped_column(String(64), nullable=False)
    department: Mapped[str | None] = mapped_column(String(128))
    contact_info: Mapped[str | None] = mapped_column(String(128))
    user_type: Mapped[str] = mapped_column(Enum("student", "employee", "admin"), nullable=False)
    status: Mapped[str] = mapped_column(Enum("normal", "disabled"), default="normal", nullable=False)
