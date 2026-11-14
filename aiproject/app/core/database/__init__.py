from collections.abc import Generator

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import PoolResetState

from app.core.config import get_settings

_CLEAR_MYSQL_USER_VARS_SQL = (
    "SET @base_org_reason = NULL, @base_org_actor_user_id = NULL"
)

# 查询超时（秒），NL2SQL 与列表接口共用
STATEMENT_TIMEOUT_SEC = 5


class Base(DeclarativeBase):
    pass


def _reset_mysql_user_context(
    dbapi_connection,
    connection_record,
    reset_state: PoolResetState,
) -> None:
    """Clear connection-scoped MySQL user variables before the pool returns the connection."""
    if reset_state.terminate_only:
        return
    if dbapi_connection.__class__.__module__ != "pymysql.connections":
        return
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute(_CLEAR_MYSQL_USER_VARS_SQL)
    finally:
        cursor.close()


_settings = get_settings()
engine = create_engine(
    _settings.database_url,
    pool_pre_ping=True,
    pool_recycle=1800,
    connect_args={"connect_timeout": STATEMENT_TIMEOUT_SEC},
)
event.listen(engine, "reset", _reset_mysql_user_context)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def ping_database() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
