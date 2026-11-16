from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.dialects.mysql import BIGINT, MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import LargeBinary

from app.core.database import Base


LEAD_ID = BigInteger().with_variant(BIGINT(unsigned=True), "mysql")


class CustomerIdentity(Base):
    __tablename__ = "crm_customer_identity"

    lead_id: Mapped[int] = mapped_column(LEAD_ID, ForeignKey("crm_lead.id"), primary_key=True, autoincrement=False)
    verified_name: Mapped[str] = mapped_column(String(64))
    verified_mobile: Mapped[str] = mapped_column(String(11), unique=True)
    verified_by: Mapped[int] = mapped_column(BigInteger)
    verified_at: Mapped[datetime] = mapped_column(DateTime)


class CustomerImportPreview(Base):
    __tablename__ = "crm_customer_import_preview"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    lead_id: Mapped[int] = mapped_column(LEAD_ID, ForeignKey("crm_lead.id"), index=True)
    actor_kind: Mapped[str] = mapped_column(String(12))
    actor_id: Mapped[int] = mapped_column(BigInteger)
    profile_version: Mapped[int] = mapped_column(Integer)
    file_name: Mapped[str] = mapped_column(String(255))
    file_content: Mapped[bytes] = mapped_column(LargeBinary().with_variant(MEDIUMBLOB(), "mysql"))
    raw_content: Mapped[str] = mapped_column(Text)
    proposed: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
