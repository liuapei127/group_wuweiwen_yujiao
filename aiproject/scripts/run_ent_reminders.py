"""python -m scripts.run_ent_reminders --once 或 --interval 60；部署方独立运行。"""
import argparse
import logging
import time
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.security.base_session import purge_expired_families
from app.modules.auth.service_identity import purge_expired_sessions
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
    while True:
        try:
            with SessionLocal() as db:
                result = scan_reminders(db)
                result["academic_notifications_processed"] = scan_academic_reminders(db)
                result["report_snapshots_created"] = scan_reports(db)
                if get_settings().employee_identity_mode == "base_rs256" and time.monotonic() >= next_base_cleanup:
                    result["expired_base_families_removed"] = purge_expired_families(db)
                    result["expired_service_sessions_removed"] = purge_expired_sessions(db)
                    result["expired_primary_organizations_removed"] = clear_expired_primary(db)
                    next_base_cleanup = time.monotonic() + 3600
                print(result, flush=True)
        except Exception:
            logging.exception("扫描失败，本轮事务回滚")
            if args.once:raise
        if args.once:break
        time.sleep(args.interval)

if __name__=="__main__":main()
