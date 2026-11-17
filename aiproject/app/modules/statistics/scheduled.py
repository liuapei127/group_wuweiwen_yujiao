import logging
from datetime import datetime, timedelta

from fastapi.encoders import jsonable_encoder
from sqlalchemy import insert, update
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.security import EmployeePrincipal
from app.modules.auth.repository import AuthRepository
from app.modules.organization.membership import managed_employees_query

from . import board_service, wellbeing
from . import repository as statistics_repository
from . import scheduled_repository as repository, service
from .periods import beijing_now as _now, week_bounds, week_monday
from .schemas import ScheduleKind, ScheduleWrite
from .analysis_models import ReportScheduleOptions

logger = logging.getLogger(__name__)

REPORTS = {
    "customer_ops": ("客户经营日报", "reports:operations:read"),
    "daily_summary": ("员工日报提交汇总", "reports:summary:read"),
    "weekly_summary": ("员工周报提交汇总", "reports:summary:read"),
    "psych_weekly": ("心理预警周报", "student-alerts:read"),
    "complaint_weekly": ("投诉周报", "reports:operations:read"),
}
_WEEKLY = {"weekly_summary", "psych_weekly", "complaint_weekly"}


def _allowed_kinds(db: Session, principal: EmployeePrincipal, *, archive: bool = False) -> tuple[str, ...]:
    kinds = []
    for kind, (_, permission) in REPORTS.items():
        if kind == "psych_weekly":
            if (archive if wellbeing.can_view_all_weeks(principal) else permission in principal.permissions):
                kinds.append(kind)
            continue
        if permission not in principal.permissions:
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
    rows = {}
    for row in repository.own_schedules(db, principal.employee_id):
        if row["report_type"] not in kinds:
            continue
        option = db.get(ReportScheduleOptions, row["id"])
        rows[row["report_type"]] = {**_schedule_view(row), "include_ai": bool(option and option.include_ai)}
    return {"items": [
        {"kind": kind, "title": REPORTS[kind][0], "weekly": kind in _WEEKLY,
         "run_at": "09:00", "enabled": False, "include_ai": False, "last_run_time": None, **rows.get(kind, {})}
        for kind in kinds
    ]}


def configure(db: Session, principal: EmployeePrincipal, payload: ScheduleWrite):
    if payload.kind not in _allowed_kinds(db, principal):
        raise BusinessError(403, "缺少该报表的查看权限")
    if payload.include_ai and payload.kind in ("daily_summary", "weekly_summary"):
        from app.core.security.authorization import require_permission
        require_permission(principal, "reports:formal:generate")
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
            schedule_id = previous["id"]
            db.execute(update(repository.schedules).where(repository.schedules.c.id == previous["id"]).values(**values))
        else:
            result = db.execute(insert(repository.schedules).values(
                **values, report_type=payload.kind, recipients=[principal.employee_id], create_time=now,
            ))
            schedule_id = result.lastrowid
        if payload.include_ai is not None:
            option = db.get(ReportScheduleOptions, schedule_id)
            if option is None:
                option = ReportScheduleOptions(schedule_id=schedule_id)
                db.add(option)
            option.include_ai = payload.include_ai
        db.commit()
    except Exception:
        db.rollback()
        raise
    return preferences(db, principal)


def archive(db: Session, principal: EmployeePrincipal, before_id: int | None, *,
            kind: ScheduleKind | None = None, limit: int = 20, shared: bool = False):
    kinds = _allowed_kinds(db, principal, archive=True)
    if kind is not None:
        kinds = (kind,) if kind in kinds else ()
    if not kinds:
        raise BusinessError(403, "缺少报表归档权限")
    department, members = _current_scope(db, principal, kinds)
    if shared:
        return _shared_archive(db, principal, kinds, before_id, limit, department, members)
    rows = repository.own_reports(db, principal.employee_id, kinds, before_id, limit)
    students = (wellbeing.weekly_student_ids(db, principal)
                if any(row["report_type"] == "psych_weekly" for row in rows) else frozenset())
    return [_visible_report(row, principal, department, members, students) for row in rows]


def archived_report(db: Session, principal: EmployeePrincipal, report_id: int, *, shared: bool = False) -> dict:
    kinds = _allowed_kinds(db, principal, archive=True)
    if not kinds:
        raise BusinessError(403, "缺少报表归档权限")
    row = repository.report_candidate(db, report_id, kinds) if shared else repository.own_report(
        db, principal.employee_id, kinds, report_id)
    if row is None:
        raise BusinessError(404, "报告不存在")
    department, members = _current_scope(db, principal, (row["report_type"],))
    if shared and row["report_type"] != "psych_weekly" and row["generated_by"] not in _shared_owners(db, principal, department, members):
        raise BusinessError(404, "报告不存在或不在授权范围")
    students = (wellbeing.weekly_student_ids(db, principal)
                if row["report_type"] == "psych_weekly" else frozenset())
    visible = _visible_report(row, principal, department, members, students)
    if visible.get("unavailable"):
        raise BusinessError(403, "当前权限范围已变更，无法下载该报告")
    db.rollback()
    return visible


def _shared_owners(db, principal, department, members):
    if department is None and principal.role_code == "admin":
        from app.modules.student_admin.models import SysUser
        from sqlalchemy import select
        return set(db.scalars(select(SysUser.id).where(SysUser.user_type.in_(("employee", "admin")))))
    return members | {principal.employee_id}


def _shared_archive(db, principal, kinds, before_id, limit, department, members):
    owners = _shared_owners(db, principal, department, members)
    students = wellbeing.weekly_student_ids(db, principal) if "psych_weekly" in kinds else frozenset()
    result = []
    cursor = before_id
    while len(result) < limit:
        rows = repository.shared_candidates(db, owners, kinds, cursor, 100)
        if not rows:
            break
        for row in rows:
            visible = _visible_report(row, principal, department, members, students)
            if not visible.get("unavailable"):
                result.append(visible)
                if len(result) == limit:
                    break
        cursor = rows[-1]["id"]
    return result


def _current_scope(db: Session, principal: EmployeePrincipal, kinds: tuple[str, ...]):
    if all(kind == "psych_weekly" for kind in kinds):
        return None, set()
    department = service._report_department(db, principal)
    if isinstance(department, int):
        return department, set(db.scalars(managed_employees_query(department)))
    if department is not None:
        return department, statistics_repository.active_department_members(db, department)
    return None, set()


def _visible_report(row: dict, principal: EmployeePrincipal, department: str | int | None,
                    department_members: set[int], student_ids: frozenset[int]) -> dict:
    scope = row.pop("report_content")
    if isinstance(scope, dict) and scope.get("scope_version") == 1:
        if row["report_type"] == "psych_weekly":
            allowed = isinstance(scope.get("student_ids"), list) and set(scope["student_ids"]).issubset(student_ids)
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
    students = frozenset()
    if kind == "psych_weekly":
        students = wellbeing.weekly_student_ids(db, principal)
        snapshot = wellbeing.week_statistics(db, anchor, students)
        scope = None
    else:
        snapshot = _snapshot(db, principal, kind, anchor, weekly_customers=weekly_customers)
        scope = service._report_department(db, principal)
    periods = jsonable_encoder(snapshot)
    option = db.get(ReportScheduleOptions, row["id"])
    formal = False
    if option and option.include_ai:
        from . import formal_dify, report_ai
        from .schemas import EmployeeReportSummary, FormalReportSections
        if kind in ("daily_summary", "weekly_summary"):
            if "reports:formal:generate" not in principal.permissions:
                return False
            period = "day" if kind == "daily_summary" else "week"
            stats = EmployeeReportSummary.model_validate(snapshot)
            text, contributors = service._report_payload(db, stats, scope, period)
            sections = formal_dify.generate_summary("daily" if period == "day" else "weekly", text) if contributors else FormalReportSections(
                work_summary="本期无相关记录", key_progress_summary="本期无相关记录",
                risk_summary="本期无相关记录", next_work_suggestions="本期无相关记录")
            periods["sections"] = sections.model_dump()
            formal = True
        elif kind == "customer_ops":
            periods["ai_summary"] = report_ai.customer_summary(periods)
        elif kind == "psych_weekly" and periods["suppressed"]:
            periods["ai_status"] = "参与人数低于展示门槛，本次归档统计快照"
        else:
            periods["ai_summary"] = report_ai.suggest("心理周报" if kind == "psych_weekly" else "投诉", periods)
    department_members = sorted(db.scalars(managed_employees_query(scope))) if isinstance(scope, int) else None
    payload = {**periods, "scope_version": 1, "department": periods.get("department"),
               "department_members": department_members,
               "student_ids": sorted(students),
               "statistics": periods}
    if formal:
        payload.update(format="formal", contributor_ids=sorted(contributors))
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
    start, end = week_bounds(anchor) if kind == "complaint_weekly" or weekly_customers else (anchor, anchor)
    data = board_service.operations(db, principal, "complaints" if kind == "complaint_weekly" else "customers", start, end)
    data.pop("items", None)
    data.pop("has_more", None)
    return data
