from sqlalchemy import Table, Column, BigInteger, Integer, SmallInteger, String, Text, DateTime, Numeric, Enum, LargeBinary
from app.core.database import Base

onboarding_guide = Table("onboarding_guide", Base.metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True),
    Column("title", String(255), nullable=False),
    Column("category", String(64), nullable=False),
    Column("content", Text, nullable=False),
    Column("embedding_vector", LargeBinary, nullable=True),
    Column("sort_order", Integer, nullable=False),
    Column("status", SmallInteger, nullable=False),
    Column("create_time", DateTime, nullable=False),
    Column("update_time", DateTime, nullable=False),
)
