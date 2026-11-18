"""Import the reviewed presentation snapshot into an empty local MySQL database."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
from pathlib import Path

import pymysql

from app.core.config import get_settings


def statements(path):
    delimiter=';'
    buffer=[]
    with gzip.open(path,'rt',encoding='utf-8') as stream:
        for line in stream:
            stripped=line.strip()
            if not stripped or stripped.startswith('--'): continue
            if stripped.startswith('DELIMITER '):
                if buffer: raise ValueError('Unexpected SQL delimiter')
                delimiter=stripped.split()[1]
                continue
            buffer.append(line.rstrip('\n'))
            if stripped.endswith(delimiter):
                yield '\n'.join(buffer).rstrip()[:-len(delimiter)]
                buffer=[]
    if buffer: raise ValueError('Incomplete SQL export')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True,help='Explicit target database; existing populated databases are refused')
    parser.add_argument('--bundle',type=Path,default=Path('docs/team-delivery/2026-11-18/database'))
    args=parser.parse_args()
    settings=get_settings()
    if settings.db_host not in {'localhost','127.0.0.1','::1'}: raise SystemExit('Import is limited to local MySQL')
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,62}',args.database): raise SystemExit('Invalid database name')
    manifest=json.loads((args.bundle/'manifest.json').read_text(encoding='utf-8'))
    source=args.bundle/manifest['sql_file']
    if source.resolve().parent!=args.bundle.resolve(): raise SystemExit('Invalid SQL path')
    if manifest['kind']!='synthetic_showcase' or hashlib.sha256(source.read_bytes()).hexdigest()!=manifest['sha256']:
        raise SystemExit('Snapshot integrity check failed')
    conn=pymysql.connect(host=settings.db_host,port=settings.db_port,user=settings.db_user,password=settings.db_password,charset='utf8mb4',autocommit=False)
    try:
        with conn.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA=%s',(args.database,))
            if cursor.fetchone()[0]: raise SystemExit('Target is not empty; choose a new database. No data was replaced.')
            cursor.execute(f'CREATE DATABASE IF NOT EXISTS `{args.database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
            conn.select_db(args.database)
            for statement in statements(source): cursor.execute(statement)
            for name,expected in manifest['row_counts'].items():
                if not re.fullmatch(r'[a-zA-Z0-9_]+',name): raise ValueError('Invalid table name')
                cursor.execute(f'SELECT COUNT(*) FROM `{name}`')
                actual=cursor.fetchone()[0]
                if actual!=expected: raise RuntimeError(f'{name}: expected {expected}, got {actual}')
            cursor.execute('SHOW TRIGGERS')
            if sorted(row[0] for row in cursor.fetchall())!=sorted(manifest['triggers']): raise RuntimeError('Trigger verification failed')
            cursor.execute('''SELECT TABLE_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME
                FROM information_schema.KEY_COLUMN_USAGE
                WHERE TABLE_SCHEMA=%s AND REFERENCED_TABLE_NAME IS NOT NULL''',(args.database,))
            for child,column,parent,parent_column in cursor.fetchall():
                cursor.execute(f'SELECT COUNT(*) FROM `{child}` c LEFT JOIN `{parent}` p ON c.`{column}`=p.`{parent_column}` WHERE c.`{column}` IS NOT NULL AND p.`{parent_column}` IS NULL')
                if cursor.fetchone()[0]: raise RuntimeError('Broken foreign key: '+child+'.'+column)
            cursor.execute('''SELECT COUNT(*) FROM website_student_access a
                JOIN visitor_account v ON v.id=a.visitor_id JOIN sys_user u ON u.id=a.student_id
                JOIN visitor_intake i ON i.visitor_id=v.id JOIN crm_lead l ON l.id=i.crm_lead_id
                WHERE v.name COLLATE utf8mb4_unicode_ci<>u.real_name OR v.name COLLATE utf8mb4_unicode_ci<>l.customer_name''')
            if cursor.fetchone()[0]: raise RuntimeError('Student/customer identity mismatch')
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()
    print(f'Imported and verified {len(manifest["row_counts"])} tables in local database {args.database}.')
    print('Configure DB_NAME='+args.database+' in your local .env. Existing source databases were not changed.')


if __name__=='__main__': main()
