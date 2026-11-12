"""Authentication persistence plus projections of existing user/role tables."""
from sqlalchemy import Table, Column, BigInteger, Integer, String, Text, DateTime, SmallInteger, column, table
from app.core.database import Base
from app.core.security.credentials import utc_now

# sys_user remains the existing shared identity table. Its business ORM only maps
# a subset; this full SQL projection avoids redefining that table or migrating it.
accounts = table('sys_user', *[column(n,t) for n,t in [
    ('id',BigInteger),('username',String),('password_hash',String),('real_name',String),
    ('user_type',String),('role_id',BigInteger),('department',String),('contact_info',String),
    ('avatar_url',String),('status',String),('create_time',DateTime),('update_time',DateTime)]])
roles = Table('sys_role',Base.metadata,
    Column('id',BigInteger().with_variant(Integer,'sqlite'),primary_key=True,autoincrement=True),
    Column('role_code',String(32),nullable=False,unique=True),Column('role_name',String(64),nullable=False),
    Column('description',String(255)),Column('status',SmallInteger,nullable=False,default=1),
    Column('create_time',DateTime,nullable=False,default=utc_now),Column('update_time',DateTime,nullable=False,default=utc_now))
role_permissions = Table('ent_auth_role_permission',Base.metadata,
    Column('role_id',BigInteger,primary_key=True),Column('permission',String(96),primary_key=True))
student_scopes = Table('ent_auth_student_scope',Base.metadata,
    Column('user_id',BigInteger,primary_key=True),Column('student_id',BigInteger,primary_key=True))
sessions = Table('ent_auth_session',Base.metadata,
    Column('id',String(36),primary_key=True),Column('user_id',BigInteger,nullable=False,index=True),
    Column('expires_at',DateTime,nullable=False),Column('revoked_at',DateTime),
    Column('create_time',DateTime,nullable=False,default=utc_now))
login_attempts = Table('ent_auth_login_attempt',Base.metadata,
    Column('id',BigInteger().with_variant(Integer,'sqlite'),primary_key=True,autoincrement=True),
    Column('attempt_key',String(64),nullable=False,index=True),Column('create_time',DateTime,nullable=False,default=utc_now))
audit_log = Table('ent_auth_audit',Base.metadata,
    Column('id',BigInteger().with_variant(Integer,'sqlite'),primary_key=True,autoincrement=True),
    Column('actor_id',BigInteger),Column('action',String(64),nullable=False),Column('target',String(128)),
    Column('details',Text,nullable=False,default='{}'),Column('create_time',DateTime,nullable=False,default=utc_now))
AUTH_NEW_TABLES = [role_permissions,student_scopes,sessions,login_attempts,audit_log]

for _table in AUTH_NEW_TABLES:
    _table.dialect_options["mysql"].update(engine="InnoDB",charset="utf8mb4",collate="utf8mb4_unicode_ci")
