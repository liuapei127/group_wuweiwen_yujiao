"""BASE session tables. Separate metadata so ENT inserts stay unchanged."""
from sqlalchemy import BigInteger, Column, DateTime, MetaData, String, Table

metadata = MetaData()

base_sessions = Table(
    "ent_auth_session",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("user_id", BigInteger, nullable=False),
    Column("expires_at", DateTime, nullable=False),
    Column("revoked_at", DateTime),
    Column("create_time", DateTime, nullable=False),
    Column("last_used_at", DateTime),
    Column("parent_session_id", String(36)),
)

refresh_tokens = Table(
    "auth_refresh_token",
    metadata,
    Column("token_hash", String(64), primary_key=True),
    Column("family_id", String(36), nullable=False, index=True),
    Column("session_id", String(36), nullable=False, index=True),
    Column("user_id", BigInteger, nullable=False, index=True),
    Column("expires_at", DateTime, nullable=False),
    Column("used_at", DateTime),
    Column("revoked_at", DateTime),
    Column("replaced_by", String(64)),
)

session_kids = Table(
    "auth_user_session_kid",
    metadata,
    Column("session_id", String(36), primary_key=True),
    Column("kid", String(64), primary_key=True),
    Column("first_issued_at", DateTime, nullable=False),
)
