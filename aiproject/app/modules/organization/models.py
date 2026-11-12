from sqlalchemy import Table, Column, BigInteger, Integer, SmallInteger, String, Text, DateTime, Numeric, Enum, LargeBinary
from app.core.database import Base

sys_organization = Table("sys_organization", Base.metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True),
    Column("org_name", String(128), nullable=False),
    Column("parent_id", BigInteger, nullable=True),
    Column("org_level", SmallInteger, nullable=False),
    Column("manager_id", BigInteger, nullable=True),
    Column("sort_order", Integer, nullable=False),
    Column("status", SmallInteger, nullable=False),
    Column("create_time", DateTime, nullable=False),
    Column("update_time", DateTime, nullable=False),
)
