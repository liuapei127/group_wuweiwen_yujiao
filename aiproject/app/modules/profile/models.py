from datetime import datetime
from decimal import Decimal
from typing import Any, Optional
import enum

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Index, Integer, JSON, LargeBinary, Numeric, String, Text, func
from sqlalchemy.dialects.mysql import BIGINT, MEDIUMBLOB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _id_column():
    return mapped_column(BigInteger().with_variant(Integer, "sqlite").with_variant(BIGINT(unsigned=True), "mysql"), primary_key=True, autoincrement=True)


class SourceType(str, enum.Enum):
    text = "text"
    pdf_resume = "pdf_resume"
    excel = "excel"
    import_ = "import"
    manual = "manual"


class ParseStatus(str, enum.Enum):
    pending = "pending"
    success = "success"
    failed = "failed"


class MatchResult(str, enum.Enum):
    matched = "matched"
    partial = "partial"
    not_matched = "not_matched"


class CustomerSource(Base):
    """客户原始资料表"""
    __tablename__ = "customer_source"
    __table_args__ = (
        Index("idx_source_type", "source_type"),
        Index("idx_parse_status", "parse_status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"},
    )

    id: Mapped[int] = _id_column()
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType, values_callable=lambda x: [e.value for e in x]), nullable=False, comment="资料来源类型")
    raw_content: Mapped[Optional[str]] = mapped_column(Text, comment="原始文本内容")
    file_url: Mapped[Optional[str]] = mapped_column(String(512), comment="文件存储地址")
    file_name: Mapped[Optional[str]] = mapped_column(String(255), comment="原始文件名")
    lead_id: Mapped[int | None] = mapped_column(BigInteger().with_variant(BIGINT(unsigned=True), "mysql"), ForeignKey("crm_lead.id"))
    file_content: Mapped[bytes | None] = mapped_column(LargeBinary().with_variant(MEDIUMBLOB(), "mysql"), deferred=True)
    parse_status: Mapped[ParseStatus] = mapped_column(Enum(ParseStatus, values_callable=lambda x: [e.value for e in x]), nullable=False, default=ParseStatus.pending, comment="解析状态")
    parse_result: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, comment="解析结果JSON")
    parse_error: Mapped[Optional[str]] = mapped_column(Text, comment="解析失败原因")
    operator_id: Mapped[Optional[int]] = mapped_column(BigInteger, comment="操作人用户ID")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")

    profiles: Mapped[list["CustomerProfile"]] = relationship(
        back_populates="source"
    )


class CustomerProfile(Base):
    """客户画像研判结果表"""
    __tablename__ = "customer_profile"
    __table_args__ = (
        Index("idx_source_id", "source_id"),
        Index("idx_customer_profile_lead", "lead_id", "id"),
        Index("idx_match_result", "match_result"),
        Index("idx_matched_product", "matched_product"),
    )

    id: Mapped[int] = _id_column()
    customer_name: Mapped[Optional[str]] = mapped_column(String(64), comment="客户姓名")
    contact_info: Mapped[Optional[str]] = mapped_column(String(128), comment="联系方式")
    source_id: Mapped[Optional[int]] = mapped_column(BigInteger().with_variant(BIGINT(unsigned=True), "mysql"), ForeignKey("customer_source.id"), comment="来源资料ID")
    lead_id: Mapped[int | None] = mapped_column(BigInteger().with_variant(BIGINT(unsigned=True), "mysql"), ForeignKey("crm_lead.id"))
    profile_version: Mapped[int | None] = mapped_column(Integer)
    background_info: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, comment="背景信息JSON")
    match_result: Mapped[Optional[MatchResult]] = mapped_column(Enum(MatchResult, values_callable=lambda x: [e.value for e in x]), comment="匹配结论")
    matched_product: Mapped[Optional[str]] = mapped_column(String(128), comment="匹配产品线")
    match_score: Mapped[Optional[Decimal]] = mapped_column(Numeric(5, 2), comment="匹配得分")
    match_reason: Mapped[Optional[str]] = mapped_column(Text, comment="匹配理由")
    recommended_programs: Mapped[Optional[list[Any]]] = mapped_column(JSON, comment="推荐专业/项目列表")
    evaluator_id: Mapped[Optional[int]] = mapped_column(BigInteger, comment="研判人ID")
    create_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), comment="创建时间")
    update_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    source: Mapped[Optional["CustomerSource"]] = relationship(
        back_populates="profiles"
    )


class VisitorMaterial(Base):
    __tablename__ = "visitor_material"
    __table_args__ = {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4"}

    source_id: Mapped[int] = mapped_column(ForeignKey("customer_source.id"), primary_key=True)
    visitor_id: Mapped[int] = mapped_column(ForeignKey("visitor_account.id"), index=True)
    file_content: Mapped[bytes | None] = mapped_column(LargeBinary().with_variant(MEDIUMBLOB(), "mysql"))
