import logging
from datetime import datetime, timedelta

from fastapi.encoders import jsonable_encoder
from sqlalchemy import insert, update
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.security import EmployeePrincipal
from app.modules.auth.repository import AuthRepository
from app.modules.organization.membership import managed_employees_query
from app.modules.student import alerts

from . import board_service, wellbeing
from . import repository as statistics_repository
from . import scheduled_repository as repository, service
from .periods import beijing_now as _now, week_bounds, week_monday
from .schemas import ScheduleWrite

logger = logging.getLogger(__name__)

REPORTS = {
    "customer_ops": ("客户经营日报", "reports:operations:read"),
    "daily_summary": ("员工日报提交汇总", "reports:summary:read"),
    "weekly_summary": ("员工周报提交汇总", "reports:summary:read"),
    "psych_weekly": ("心理预警周报", "student-alerts:read"),
    "complaint_weekly": ("投诉周报", "reports:operations:read"),
}
_WEEKLY = {"weekly_summary", "psych_weekly", "complaint_weekly"}


def _allowed_kinds(db: Session, principal: EmployeePrincipal) -> tuple[str, ...]:
    kinds = []
    for kind, (_, permission) in REPORTS.items():
        if permission not in principal.permissions:
            continue
        if kind == "psych_weekly":
            kinds.append(kind)
            continue
        try:
            service._report_department(db, principal)
        except BusinessError:
            continue
        kinds.append(kind)
    return tuple(kinds)


def _schedule_view(row):
    run_at = _scheduled_time(row["schedule_cron"], row["report_type"], _now())
    weekly = row["schedule_cron"].split()[-1:] == ["1"] if row["report_type"] == "customer_ops" else row["report_type"] in _WEEKLY
    return {"kind": row["report_type"], "run_at": run_at.strftime("%H:%M") if run_at else "09:00",
            "enabled": bool(row["enabled"]), "last_run_time": row["last_run_time"], "weekly": weekly}


def preferences(db: Session, principal: EmployeePrincipal):
    kinds = _allowed_kinds(db, principal)
    if not kinds:
        raise BusinessError(403, "缺少报表计划权限")
    rows = {row["report_type"]: _schedule_view(row) for row in repository.own_schedules(db, principal.employee_id)
            if row["report_type"] in kinds}
    return {"items": [
        {"kind": kind, "title": REPORTS[kind][0], "weekly": kind in _WEEKLY,
         "run_at": "09:00", "enabled": False, "last_run_time": None, **rows.get(kind, {})}
        for kind in kinds
    ]}


def configure(db: Session, principal: EmployeePrincipal, payload: ScheduleWrite):
    if payload.kind not in _allowed_kinds(db, principal):
        raise BusinessError(403, "缺少该报表的查看权限")
    if payload.weekly is not None and payload.kind != "customer_ops" and payload.weekly != (payload.kind in _WEEKLY):
        raise BusinessError(422, "此报表的生成频率固定")
    if payload.run_at.tzinfo is not None or payload.run_at.second or payload.run_at.microsecond:
        raise BusinessError(422, "请选择北京时间的小时和分钟")
    try:
        if repository.lock_employee(db, principal.employee_id) is None:
            raise BusinessError(403, "员工账号不可用")
        previous = next((row for row in repository.own_schedules(db, principal.employee_id)
                         if row["report_type"] == payload.kind), None)
        weekly = payload.kind in _WEEKLY or bool(payload.weekly)
        if payload.kind == "customer_ops" and payload.weekly is None and previous:
            weekly = _schedule_view(previous)["weekly"]
        cron = f"{payload.run_at.minute} {payload.run_at.hour} * * {1 if weekly else '*'}"
        now = _now()
        values = {"schedule_cron": cron, "enabled": int(payload.enabled), "update_time": now}
        if previous:
            db.execute(update(repository.schedules).where(repository.schedules.c.id == previous["id"]).values(**values))
        else:
            db.execute(insert(repository.schedules).values(
                **values, report_type=payload.kind, recipients=[principal.employee_id], create_time=now,
            ))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return preferences(db, principal)


def archive(db: Session, principal: EmployeePrincipal, before_id: int | None):
    kinds = _allowed_kinds(db, principal)
    if not kinds:
        raise BusinessError(403, "缺少报表归档权限")
    department, members = _current_scope(db, principal, kinds)
    return [
        _visible_report(row, principal, department, members)
        for row in repository.own_reports(db, principal.employee_id, kinds, before_id)
    ]


def archived_report(db: Session, principal: EmployeePrincipal, report_id: int) -> dict:
    kinds = _allowed_kinds(db, principal)
    if not kinds:
        raise BusinessError(403, "缺少报表归档权限")
    row = repository.own_report(db, principal.employee_id, kinds, report_id)
    if row is None:
        raise BusinessError(404, "报告不存在")
    department, members = _current_scope(db, principal, (row["report_type"],))
    visible = _visible_report(row, principal, department, members)
    if visible.get("unavailable"):
        raise BusinessError(403, "当前权限范围已变更，无法下载该报告")
    db.rollback()
    return visible


def _current_scope(db: Session, principal: EmployeePrincipal, kinds: tuple[str, ...]):
    if all(kind == "psych_weekly" for kind in kinds):
        return None, set()
    department = service._report_department(db, principal)
    if isinstance(department, int):
        return department, set(db.scalars(managed_employees_query(department)))
    if department is not None:
        return department, statistics_repository.active_department_members(db, department)
    return None, set()


def _visible_report(row: dict, principal: EmployeePrincipal, department: str | int | None, department_members: set[int]) -> dict:
    scope = row.pop("report_content")
    if isinstance(scope, dict) and scope.get("scope_version") == 1:
        if row["report_type"] == "psych_weekly":
            allowed = isinstance(scope.get("student_ids"), list) and set(scope["student_ids"]).issubset(principal.student_ids)
        elif isinstance(department, int):
            recorded = scope.get("department_members")
            allowed = isinstance(recorded, list) and set(recorded).issubset(department_members)
        else:
            allowed = scope.get("department") == department and scope.get("department_members") is None
        formal = scope.get("format") == "formal"
        if formal:
            contributors = scope.get("contributor_ids")
            allowed = allowed and "reports:formal:generate" in principal.permissions and (
                department is None or isinstance(contributors, list) and set(contributors).issubset(department_members)
            )
        if allowed and isinstance(scope.get("statistics"), dict):
            return {**row, "report_content": scope["statistics"], **({"format": "formal"} if formal else {})}
    return {"id": row["id"], "unavailable": True}


def scan_reports(db: Session) -> int:
    generated = 0
    after_id = 0
    now = _now()
    first_error = None
    while ids := repository.enabled_ids(db, after_id):
        for schedule_id in ids:
            try:
                row = repository.lock_schedule(db, schedule_id)
                created = _generate_due_report(db, row, now)
                db.commit()
                generated += int(created)
            except Exception as exc:
                db.rollback()
                logger.exception("报表计划 %s 生成失败，将在下次扫描重试", schedule_id)
                first_error = first_error or exc
        after_id = ids[-1]
    if first_error is not None:
        raise first_error
    return generated


def _generate_due_report(db: Session, row, now: datetime) -> bool:
    if row is None or row["enabled"] != 1 or row["report_type"] not in REPORTS:
        return False
    kind = row["report_type"]
    timing = _scheduled_time(row["schedule_cron"], kind, now)
    if timing is None or timing > now or row["create_time"].date() > timing.date():
        return False
    if row["last_run_time"] and row["last_run_time"].date() >= timing.date():
        return False
    recipients = row["recipients"]
    if not isinstance(recipients, list) or len(recipients) != 1 or type(recipients[0]) is not int:
        return False
    identity = AuthRepository(db)
    employee_id = recipients[0]
    employee = identity.account(user_id=employee_id)
    if (not employee or employee["status"] != "normal" or employee["user_type"] not in ("employee", "admin")
            or employee["role_status"] != 1):
        return False
    principal = EmployeePrincipal(
        employee_id, frozenset(identity.permissions(employee["role_id"])),
        frozenset(identity.scope(employee_id)), role_code=employee["role_code"],
    )
    if kind not in _allowed_kinds(db, principal):
        return False
    weekly_customers = kind == "customer_ops" and row["schedule_cron"].split()[-1:] == ["1"]
    anchor = timing.date() - timedelta(days=1)
    snapshot = _snapshot(db, principal, kind, anchor, weekly_customers=weekly_customers)
    periods = jsonable_encoder(snapshot)
    scope = service._report_department(db, principal) if kind != "psych_weekly" else None
    department_members = sorted(db.scalars(managed_employees_query(scope))) if isinstance(scope, int) else None
    payload = {**periods, "scope_version": 1, "department": periods.get("department"),
               "department_members": department_members,
               "student_ids": sorted(principal.student_ids) if kind == "psych_weekly" else [],
               "statistics": periods}
    repository.record_report(db, employee_id, kind, "客户经营周报" if weekly_customers else REPORTS[kind][0], payload, now)
    db.execute(update(repository.schedules).where(repository.schedules.c.id == row["id"]).values(last_run_time=now))
    return True


def _scheduled_time(spec: str, kind: str, now: datetime) -> datetime | None:
    parts = spec.split()
    weekly = kind in _WEEKLY or (kind == "customer_ops" and parts[-1:] == ["1"])
    if len(parts) != 5 or parts[2:] != ["*", "*", "1" if weekly else "*"]:
        return None
    try:
        minute, hour = map(int, parts[:2])
        anchor = week_monday(now.date()) if weekly else now.date()
        return now.replace(year=anchor.year, month=anchor.month, day=anchor.day, hour=hour, minute=minute, second=0)
    except ValueError:
        return None


def _snapshot(db: Session, principal: EmployeePrincipal, kind: str, anchor, *, weekly_customers=False):
    if kind in ("daily_summary", "weekly_summary"):
        period = "day" if kind == "daily_summary" else "week"
        data = service.employee_report_summary(db, principal, anchor, period).model_dump()
        submissions = board_service.employee_board(db, principal, anchor, period, None, None, 0, 1)
        data["submissions"] = {key: submissions[key] for key in ("expected", "submitted", "missing", "departments")}
        return data
    if kind == "psych_weekly":
        return wellbeing.desk_week(db, principal, anchor)
    start, end = week_bounds(anchor) if kind == "complaint_weekly" or weekly_customers else (anchor, anchor)
    data = board_service.operations(db, principal, "complaints" if kind == "complaint_weekly" else "customers", start, end)
    data.pop("items", None)
    data.pop("has_more", None)
    return data
