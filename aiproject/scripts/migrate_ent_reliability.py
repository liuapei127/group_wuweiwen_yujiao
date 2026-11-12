"""Additive local MySQL migration 001; rerunnable, never drops existing data.
Run: python -m scripts.migrate_ent_reliability --apply
MySQL DDL commits implicitly: preflight runs first; interrupted migrations can resume.
"""
import argparse
import json
import re
from collections import Counter
from pathlib import Path
from sqlalchemy import MetaData, inspect, select, text, update
from app.core.config import get_settings
from app.core.database import engine
from app.modules.score.identity import default_exam_key, submission_hash
from app.shared.utils.serialization import json_snapshot
from app.shared.utils.time_util import now_naive

ROOT = Path(__file__).resolve().parents[1]
EXPECTED = ROOT / 'migrations' / '001_ent_reliability_expected.sql'
COLUMNS = {
    'student_score': {'exam_key':'VARCHAR(96) NULL','submission_key':'VARCHAR(96) NULL','submission_hash':'VARCHAR(64) NULL','version':'INT NOT NULL DEFAULT 1','update_time':'DATETIME NULL'},
    'todo_item': {'assignment_version':'INT NOT NULL DEFAULT 1','source_status':'VARCHAR(32) NULL'},
    'notification_log': {'dedup_key':'VARCHAR(128) NULL'},
}
INDEXES = {
    'student_score': {'uk_score_exam':['student_id','exam_key'],'uk_score_submission':['student_id','submission_key']},
    'todo_item': {'uk_todo_source':['related_type','related_id']},
    'notification_log': {'uk_notification_dedup':['dedup_key']},
}


def migrate(target_engine):
    actions=[]
    with target_engine.connect() as c:
        if c.execute(text("SELECT GET_LOCK(CONCAT(DATABASE(),'_ent_migration_001'),10)")).scalar_one()!=1:
            raise RuntimeError('Migration lock unavailable')
        c.commit()
        try:
            duplicates=c.execute(text('SELECT related_type,related_id,COUNT(*) n FROM todo_item WHERE related_type IS NOT NULL AND related_id IS NOT NULL GROUP BY related_type,related_id HAVING n>1')).all()
            if duplicates:
                raise RuntimeError('Duplicate source todos need explicit reconciliation; no records deleted')
            for table,columns in COLUMNS.items():
                existing={col['name'] for col in inspect(c).get_columns(table)}
                for column,ddl in columns.items():
                    if column not in existing:
                        c.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {ddl}'))
                        c.commit()
                        actions.append(f'add {table}.{column}')
            if 'student_score_history' not in inspect(c).get_table_names():
                source=EXPECTED.read_text(encoding='utf-8')
                statement=re.search(r'CREATE TABLE \x60student_score_history\x60.*?;',source,re.S).group()
                c.execute(text(statement));c.commit()
                actions.append('create student_score_history')
            metadata=MetaData();metadata.reflect(c);c.rollback()
            scores=metadata.tables['student_score'];history=metadata.tables['student_score_history']
            with c.begin():
                rows=list(c.execute(select(scores).order_by(scores.c.id).with_for_update()).mappings())
                counts=Counter((r['student_id'],default_exam_key(r['course_name'],r['semester'])) for r in rows)
                for original in rows:
                    row=dict(original)
                    key=row['exam_key'] or (default_exam_key(row['course_name'],row['semester']) if counts[(row['student_id'],default_exam_key(row['course_name'],row['semester']))]==1 else 'legacy:'+str(row['id']))
                    values={'student_id':row['student_id'],'course_name':row['course_name'],'score':row['score'],'semester':row['semester'],'credit':row['credit'],'exam_key':key}
                    if not row['exam_key'] or not row['submission_hash']:
                        c.execute(update(scores).where(scores.c.id==row['id']).values(exam_key=key,submission_hash=row['submission_hash'] or submission_hash(values)))
                        row.update(exam_key=key,submission_hash=row['submission_hash'] or submission_hash(values))
                        actions.append('baseline score '+str(row['id']))
                    if not c.execute(select(history.c.id).where(history.c.score_id==row['id'],history.c.version==row['version'])).first():
                        c.execute(history.insert().values(score_id=row['id'],version=row['version'],operation='baseline',changed_by=row['recorded_by'],change_reason='Migration baseline; earlier revisions unknown',before_data=None,after_data=json_snapshot(row),create_time=now_naive()))
            for table,indexes in INDEXES.items():
                existing={idx['name']:idx for idx in inspect(c).get_indexes(table)}
                for name,columns in indexes.items():
                    if name in existing:
                        if not existing[name]['unique'] or existing[name]['column_names']!=columns:
                            raise RuntimeError('Conflicting index definition: '+name)
                        continue
                    c.execute(text(f"ALTER TABLE {table} ADD UNIQUE KEY {name} ({','.join(columns)})"));c.commit()
                    actions.append('unique '+name)
            c.commit()
            # Legacy system reminders retain their sent status and receive a dedup key.
            with c.begin():
                legacy = c.execute(text("SELECT n.id,n.user_id,n.related_id,t.assignment_version FROM notification_log n JOIN todo_item t ON n.related_type='todo_item' AND n.related_id=t.id AND n.user_id=t.assignee_id WHERE n.channel='system' AND n.notification_type='todo_due' AND n.dedup_key IS NULL ORDER BY n.id")).mappings().all()
                for notice in legacy:
                    key=f"todo:{notice['related_id']}:{notice['user_id']}:{notice['assignment_version']}"
                    if not c.execute(text("SELECT id FROM notification_log WHERE dedup_key=:key"),{'key':key}).first():
                        c.execute(text("UPDATE notification_log SET dedup_key=:key WHERE id=:id"),{'key':key,'id':notice['id']})
            return {'actions':actions,'database':c.execute(text('SELECT DATABASE()')).scalar_one(),'migration':'001_ent_reliability'}
        finally:
            c.execute(text("SELECT RELEASE_LOCK(CONCAT(DATABASE(),'_ent_migration_001'))"));c.commit()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    settings=get_settings()
    if settings.db_host not in ('127.0.0.1','localhost','::1'):
        raise SystemExit('Local database only')
    if not args.apply:
        print('Migration prepared. Use --apply for additive local changes.');return
    print(json.dumps(migrate(engine),ensure_ascii=False))


if __name__=='__main__':
    main()
