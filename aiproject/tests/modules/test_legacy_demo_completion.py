"""Local placeholder insertion must preserve existing data and reject ID conflicts."""
import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select
from scripts.local_ent_validation import complete_legacy_demo_users


@pytest.fixture
def database():
    metadata = MetaData()
    users = Table("sys_user", metadata, Column("id", Integer, primary_key=True),
        Column("username", String, unique=True), Column("password_hash", String),
        Column("real_name", String), Column("user_type", String), Column("role_id", Integer),
        Column("department", String), Column("contact_info", String), Column("status", String))
    roles = Table("sys_role", metadata, Column("id", Integer, primary_key=True), Column("role_code", String))
    leads = Table("crm_lead", metadata, Column("id", Integer, primary_key=True), Column("owner_employee_id", Integer))
    follows = Table("crm_follow_up", metadata, Column("id", Integer, primary_key=True), Column("employee_id", Integer))
    engine = create_engine("sqlite://")
    metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(roles.insert().values(id=10, role_code="employee"))
        conn.execute(users.insert().values(id=99, username="existing_fixture", user_type="employee", status="normal", password_hash="unchanged"))
        conn.execute(leads.insert(), [{"id":1,"owner_employee_id":1},{"id":2,"owner_employee_id":2}])
        conn.execute(follows.insert().values(id=1, employee_id=1))
        yield conn, metadata, users
    engine.dispose()


def test_completion_is_idempotent_disabled_and_preserves_existing(database):
    conn, metadata, users = database
    existing = dict(conn.execute(select(users).where(users.c.id == 99)).mappings().one())
    first = complete_legacy_demo_users(conn, metadata)
    assert first["created_total"] == 2
    assert first["linked_customer_counts"] == {1:1,2:1}
    assert first["linked_follow_up_count"] == 1
    assert complete_legacy_demo_users(conn, metadata)["created_total"] == 0
    placeholders = conn.execute(select(users).where(users.c.id.in_([1,2]))).mappings().all()
    assert all(row["status"] == "disabled" and row["password_hash"] == "!ENT_LEGACY_NO_LOGIN!" for row in placeholders)
    assert dict(conn.execute(select(users).where(users.c.id == 99)).mappings().one()) == existing


def test_id_conflict_refuses_without_partial_inserts(database):
    conn, metadata, users = database
    conn.execute(users.insert().values(id=2, username="occupied_fixture", user_type="employee", status="normal", password_hash="unchanged"))
    with pytest.raises(RuntimeError, match="refusing to overwrite"):
        complete_legacy_demo_users(conn, metadata)
    assert conn.execute(select(users.c.id).where(users.c.id == 1)).first() is None
    assert conn.execute(select(users.c.username).where(users.c.id == 2)).scalar_one() == "occupied_fixture"
