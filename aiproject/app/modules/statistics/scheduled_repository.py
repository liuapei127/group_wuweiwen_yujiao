from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, JSON, SmallInteger, String, column, insert, select, table
from sqlalchemy.orm import Session

from app.modules.auth.models import accounts

schedules = table(
    "report_schedule", column("id", BigInteger), column("report_type", String),
    column("schedule_cron", String), column("recipients", JSON), column("enabled", SmallInteger),
    column("last_run_time", DateTime), column("create_time", DateTime), column("update_time", DateTime),
)
generated = table(
    "report_generation", column("id", BigInteger), column("report_type", String),
    column("report_title", String), column("report_content", JSON), column("period_start", Date),
    column("period_end", Date), column("generated_by", BigInteger), column("status", String),
    column("create_time", DateTime),
)


def own_schedules(db: Session, employee_id: int):
    stmt = select(schedules).where(schedules.c.recipients[0].as_integer() == employee_id)
    return [row for row in db.execute(stmt.order_by(schedules.c.id)).mappings() if row["recipients"] == [employee_id]]


def lock_employee(db: Session, employee_id: int):
    return db.scalar(select(accounts.c.id).where(accounts.c.id == employee_id, accounts.c.status == "normal").with_for_update())


def lock_schedule(db: Session, schedule_id: int):
    return db.execute(select(schedules).where(schedules.c.id == schedule_id).with_for_update()).mappings().one_or_none()


def enabled_ids(db: Session, after_id: int) -> list[int]:
    return list(db.scalars(select(schedules.c.id).where(
        schedules.c.enabled == 1, schedules.c.id > after_id,
    ).order_by(schedules.c.id).limit(100)))


def record_report(db: Session, employee_id: int, kind: str, title: str, payload: dict, now: datetime):
    return db.execute(insert(generated).values(
        report_type=kind, report_title=title, report_content=payload, generated_by=employee_id,
        period_start=date.fromisoformat(payload["period_start"]), period_end=date.fromisoformat(payload["period_end"]),
        status="completed", create_time=now,
    )).lastrowid


def own_reports(db: Session, employee_id: int, kinds: tuple[str, ...], before_id: int | None):
    query = select(generated).where(
        generated.c.generated_by == employee_id, generated.c.report_type.in_(kinds),
        generated.c.status == "completed",
    )
    if before_id is not None:
        query = query.where(generated.c.id < before_id)
    return [dict(row) for row in db.execute(query.order_by(generated.c.id.desc()).limit(20)).mappings()]
