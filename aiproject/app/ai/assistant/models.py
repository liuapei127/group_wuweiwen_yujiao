from sqlalchemy import Table,Column,BigInteger,Integer,String,Text,DateTime
from app.core.database import Base
from app.core.security.credentials import utc_now

conversations=Table('ent_ai_conversation',Base.metadata,
    Column('id',String(36),primary_key=True),Column('employee_id',BigInteger,nullable=False,index=True),
    Column('title',String(128),nullable=False,default='新对话'),Column('pending',Text,nullable=False,default=''),
    Column('version',Integer,nullable=False,default=0),Column('busy_token',String(36)),Column('busy_until',DateTime),
    Column('create_time',DateTime,nullable=False,default=utc_now),Column('update_time',DateTime,nullable=False,default=utc_now))
messages=Table('ent_ai_message',Base.metadata,
    Column('id',BigInteger().with_variant(Integer,'sqlite'),primary_key=True,autoincrement=True),
    Column('conversation_id',String(36),nullable=False,index=True),Column('role',String(16),nullable=False),
    Column('content',Text,nullable=False),Column('metadata_json',Text,nullable=False,default='{}'),
    Column('create_time',DateTime,nullable=False,default=utc_now))
AI_NEW_TABLES=[conversations,messages]

for _table in AI_NEW_TABLES:
    _table.dialect_options["mysql"].update(engine="InnoDB",charset="utf8mb4",collate="utf8mb4_unicode_ci")
