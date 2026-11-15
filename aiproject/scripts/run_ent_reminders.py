"""python -m scripts.run_ent_reminders --once 或 --interval 60；部署方独立运行。"""
import argparse
import logging
import time
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security.base_session import purge_expired_families
from app.core.security.credentials import utc_now
from app.modules.auth.service_identity import purge_expired_sessions
from app.modules.customer_service.repository import purge_expired_chat_sessions
from app.modules.organization.membership import clear_expired_primary
from app.modules.todo.reminders import scan_reminders
from app.modules.student.service import scan_academic_reminders
from app.modules.statistics.scheduled import scan_reports

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--once",action="store_true")
    parser.add_argument("--interval",type=int,default=60)
    args=parser.parse_args()
    if args.interval<5:parser.error("interval 至少 5 秒")
    next_base_cleanup = 0.0
    next_cs_cleanup = 0.0
    while True:
        result = {}
        failures = []
        for key, scan in (
            (None, scan_reminders),
            ("academic_notifications_processed", scan_academic_reminders),
            ("report_snapshots_created", scan_reports),
        ):
            try:
                with SessionLocal() as db:
                    output = scan(db)
                if key is None:
                    result.update(output)
                else:
                    result[key] = output
            except Exception as exc:
                logging.exception("扫描任务失败：%s", scan.__name__)
                failures.append(exc)
        try:
            with SessionLocal() as db:
                if get_settings().employee_identity_mode == "base_rs256" and time.monotonic() >= next_base_cleanup:
                    result["expired_base_families_removed"] = purge_expired_families(db)
                    result["expired_service_sessions_removed"] = purge_expired_sessions(db)
                    result["expired_primary_organizations_removed"] = clear_expired_primary(db)
                    next_base_cleanup = time.monotonic() + 3600
        except Exception as exc:
            logging.exception("过期数据清理失败")
            failures.append(exc)
        if time.monotonic() >= next_cs_cleanup:
            try:
                with SessionLocal() as db:
                    result["expired_customer_chats_removed"] = purge_expired_chat_sessions(db, utc_now())
                next_cs_cleanup = time.monotonic() + 3600
            except Exception as exc:
                logging.exception("客服会话清理失败")
                failures.append(exc)
        print(result, flush=True)
        if args.once:
            if failures:
                raise failures[0]
            break
        time.sleep(args.interval)

if __name__=="__main__":main()
