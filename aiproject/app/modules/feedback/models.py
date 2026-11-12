from sqlalchemy import Table, Column, BigInteger, Integer, SmallInteger, String, Text, DateTime, Numeric, Enum, LargeBinary
from app.core.database import Base

student_feedback_ticket = Table("student_feedback_ticket", Base.metadata,
    Column("id", BigInteger().with_variant(Integer, "sqlite"), primary_key=True),
    Column("student_id", BigInteger, nullable=False),
    Column("ticket_type", Enum('complaint','suggestion','consult'), nullable=False),
    Column("category", String(64), nullable=True),
    Column("title", String(255), nullable=True),
    Column("content", Text, nullable=False),
    Column("detail", Text, nullable=True),
    Column("status", Enum('pending','processing','resolved','closed'), nullable=False),
    Column("priority", Enum('low','medium','high','urgent'), nullable=False),
    Column("assignee_id", BigInteger, nullable=True),
    Column("solution", Text, nullable=True),
    Column("satisfaction", SmallInteger, nullable=True),
    Column("is_notified", SmallInteger, nullable=False),
    Column("create_time", DateTime, nullable=False),
    Column("update_time", DateTime, nullable=False),
)
