from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, LargeBinary, String
from sqlalchemy.dialects.mysql import BIGINT, MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VisitorAccount(Base):
    __tablename__ = "visitor_account"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(64))
    contact: Mapped[str] = mapped_column(String(128))
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime)


class VisitorAvatar(Base):
    __tablename__ = "visitor_avatar"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    visitor_id: Mapped[int] = mapped_column(
        ForeignKey("visitor_account.id", ondelete="CASCADE"), primary_key=True, autoincrement=False,
    )
    image: Mapped[bytes] = mapped_column(LargeBinary().with_variant(MEDIUMBLOB, "mysql"))


class VisitorSession(Base):
    __tablename__ = "visitor_session"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    digest: Mapped[str] = mapped_column(String(64), primary_key=True)
    visitor_id: Mapped[int] = mapped_column(ForeignKey("visitor_account.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class WebsiteStudentAccess(Base):
    __tablename__ = "website_student_access"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    visitor_id: Mapped[int] = mapped_column(ForeignKey("visitor_account.id"), primary_key=True, autoincrement=False)
    student_id: Mapped[int] = mapped_column(BigInteger().with_variant(BIGINT(unsigned=True), "mysql"), ForeignKey("sys_user.id"), unique=True)
    enabled: Mapped[bool] = mapped_column(Boolean)
