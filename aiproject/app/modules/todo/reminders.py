"""Background transaction with bounded retries for MySQL lock conflicts."""
import time
import random
from sqlalchemy.exc import OperationalError, IntegrityError
from .reminder_repository import collect_reminders, scanner_lock


def scan_reminders(db, *, employee_ids=None):
    with scanner_lock(db) as acquired:
        if not acquired:
            return {"todos_created": 0, "system_notifications_created": 0}
        return _scan_transaction(db, employee_ids=employee_ids)


def _scan_transaction(db, *, employee_ids=None):
    for attempt in range(3):
        try:
            result = collect_reminders(db, employee_ids=employee_ids)
            db.commit()
            return result
        except (OperationalError, IntegrityError) as exc:
            db.rollback()
            code = getattr(exc.orig, "args", (None,))[0]
            if code not in (1062, 1205, 1213) or attempt == 2:
                raise
            time.sleep(random.uniform(0.02, 0.08) * (attempt + 1))
        except Exception:
            db.rollback()
            raise
