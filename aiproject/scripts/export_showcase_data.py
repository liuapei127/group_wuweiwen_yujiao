"""Export local showcase business data without live sessions or infrastructure secrets."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import MetaData, select, text

from app.core.security.credentials import hash_password
from scripts.seed_full_system_qa import _engine

# Keep the schema for these tables, but never distribute credentials/session data.
EMPTY_TABLES = {
    'ent_auth_session','auth_refresh_token','auth_user_session_kid','ent_auth_login_attempt',
    'auth_service_client','auth_service_client_audience','auth_service_session','auth_service_session_kid',
    'visitor_session','ent_auth_audit','cs_website_session','cs_short_turn',
    'ent_ai_conversation','ent_ai_message','chat_session','chat_message',
    'stu_assistant_conversation','stu_assistant_message','stu_assistant_task',
    'stu_mem0_memory','cs_visitor_memory','crm_customer_import_preview',
}
DEMO_PASSWORD = 'YuejiaoDemo_2026!'


def literal(value):
    if value is None: return 'NULL'
    if isinstance(value, bytes): return "X'" + value.hex() + "'"
    if isinstance(value, bool): return '1' if value else '0'
    if isinstance(value, (int, Decimal)): return str(value)
    if isinstance(value, float):
        if not math.isfinite(value): raise ValueError('Non-finite database number')
        return str(value)
    if isinstance(value, datetime): value = value.isoformat(sep=' ', timespec='microseconds')
    elif isinstance(value, date): value = value.isoformat()
    elif isinstance(value, (dict,list)): value=json.dumps(value,ensure_ascii=False,separators=(',',':'))
    if not isinstance(value,str): raise TypeError(type(value).__name__)
    escaped=value.replace('\\','\\\\').replace('\0','\\0').replace('\n','\\n').replace('\r','\\r').replace('\x1a','\\Z').replace("'","\\'")
    return "'" + escaped + "'"


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    engine,settings=_engine()
    if settings.db_name!='education_service': raise SystemExit('Only the reviewed local showcase database may be exported')
    args.output.mkdir(parents=True,exist_ok=True)
    sql_path=args.output/'showcase.mysql.sql.gz'
    metadata=MetaData();metadata.reflect(engine)
    demo_hash=hash_password(DEMO_PASSWORD)
    counts={};accounts=[]
    with engine.connect().execution_options(isolation_level='REPEATABLE READ') as conn, conn.begin():
        marker_count=conn.scalar(text("SELECT COUNT(*) FROM visitor_account WHERE name LIKE '%联调%' OR name LIKE '%测试%'"))
        if marker_count or conn.scalar(text('SELECT COUNT(*) FROM student_info'))!=42:
            raise SystemExit('Source is not the reviewed showcase dataset')
        with gzip.open(sql_path,'wt',encoding='utf-8',newline='\n') as stream:
            stream.write('-- Synthetic showcase dataset. Import only into a new local MySQL 8 database.\n')
            stream.write("SET NAMES utf8mb4;\nSET time_zone='+00:00';\nSET @SHOWCASE_OLD_SQL_MODE=@@SQL_MODE;\nSET SQL_MODE='STRICT_TRANS_TABLES,NO_AUTO_VALUE_ON_ZERO,ERROR_FOR_DIVISION_BY_ZERO,NO_ENGINE_SUBSTITUTION';\nSET FOREIGN_KEY_CHECKS=0;\n")
            for name in sorted(metadata.tables):
                ddl=conn.execute(text(f'SHOW CREATE TABLE `{name}`')).first()[1]
                stream.write(ddl+';\n')
            for name,table in sorted(metadata.tables.items()):
                if name in EMPTY_TABLES:
                    counts[name]=0
                    continue
                rows=conn.execute(select(table)).mappings()
                count=0
                cols=list(table.c.keys())
                header=f"INSERT INTO `{name}` ("+','.join('`'+col+'`' for col in cols)+') VALUES '
                for raw in rows:
                    row=dict(raw)
                    if name in {'sys_user','visitor_account'}:
                        # Demo credentials only; original password hashes never leave this machine.
                        row['password_hash']=demo_hash
                        if name=='visitor_account':
                            accounts.append({'type':'website','username':row['username'],'name':row['name']})
                        elif row['user_type']!='student' and row['status']=='normal':
                            accounts.append({'type':'staff','username':row['username'],'name':row['real_name'],'role_id':row['role_id']})
                    stream.write(header+'('+','.join(literal(row[col]) for col in cols)+');\n')
                    count+=1
                counts[name]=count
            # Triggers are created after loading rows, so import does not invent a second organization history.
            triggers=[]
            for row in conn.execute(text('SHOW TRIGGERS')).mappings():
                original=conn.execute(text('SHOW CREATE TRIGGER `'+row['Trigger']+'`')).mappings().first()['SQL Original Statement']
                original=re.sub(r'CREATE\s+DEFINER\s*=\s*`[^`]+`@`[^`]+`\s+', 'CREATE ',original,count=1,flags=re.I)
                stream.write('DELIMITER $$\n'+original+'$$\nDELIMITER ;\n')
                triggers.append(row['Trigger'])
            stream.write('SET FOREIGN_KEY_CHECKS=1;\nSET SQL_MODE=@SHOWCASE_OLD_SQL_MODE;\n')
        manifest={'format':1,'kind':'synthetic_showcase','mysql_version':'8.0+','source_database':settings.db_name,
                  'exported_at':datetime.now().astimezone().isoformat(),'sql_file':sql_path.name,
                  'sha256':hashlib.sha256(sql_path.read_bytes()).hexdigest(),'bytes':sql_path.stat().st_size,
                  'row_counts':counts,'empty_runtime_tables':sorted(EMPTY_TABLES),'triggers':triggers,
                  'demo_password':DEMO_PASSWORD,'accounts':accounts}
    (args.output/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'database_export':str(sql_path),'tables':len(counts),'rows':sum(counts.values()),'bytes':manifest['bytes'],'triggers':len(triggers)},ensure_ascii=False))


if __name__=='__main__': main()
