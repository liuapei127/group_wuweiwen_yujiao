"""python -m scripts.run_ent_reminders --once 或 --interval 60；部署方独立运行。"""
import argparse
import logging
import time
from app.core.database import SessionLocal
from app.modules.todo.reminders import scan_reminders

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--once",action="store_true")
    parser.add_argument("--interval",type=int,default=60)
    args=parser.parse_args()
    if args.interval<5:parser.error("interval 至少 5 秒")
    while True:
        try:
            with SessionLocal() as db:
                print(scan_reminders(db),flush=True)
        except Exception:
            logging.exception("扫描失败，本轮事务回滚")
            if args.once:raise
        if args.once:break
        time.sleep(args.interval)

if __name__=="__main__":main()
