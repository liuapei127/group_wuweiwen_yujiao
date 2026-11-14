from contextlib import closing
import json
from datetime import date, timedelta
from typing import Literal

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.core.security import EmployeePrincipal
from app.core.security.authorization import require_permission
from app.modules.organization.membership import managed_employees_query

from . import formal_dify, repository
from .periods import week_bounds
from .schemas import (
    DailySubmissionCount, EmployeeReportSummary, FormalEmployeeReport, FormalReportRequest, FormalReportSections,
)

_MAX_PAYLOAD_CHARS = 50_000
_NO_RECORDS = "本期无相关记录"


def _report_department(db: Session, principal: EmployeePrincipal) -> str | int | None:
    if principal.role_code == "admin":
        return None
    if principal.role_code == "manager":
        if get_settings().employee_identity_mode == "base_rs256":
            if db.scalar(managed_employees_query(principal.employee_id).limit(1)) is None:
                raise BusinessError(403, "当前主管尚无可查询的有效组织成员")
            return principal.employee_id
        department = repository.active_manager_department(db, principal.employee_id)
        if department and department.strip():
            return department
        raise BusinessError(403, "当前主管尚无可查询的部门")
    raise BusinessError(403, "当前角色没有报告汇总范围")


def report_scope_label(scope: str | int | None) -> str | None:
    return "所管组织及下级" if isinstance(scope, int) else scope


def employee_report_summary(
    db: Session, principal: EmployeePrincipal, anchor: date, period: Literal["day", "week"],
) -> EmployeeReportSummary:
    require_permission(principal, "reports:summary:read")
    department = _report_department(db, principal)

    try:
        start, end = week_bounds(anchor) if period == "week" else (anchor, anchor)
    except OverflowError as exc:
        raise BusinessError(422, "该日期无法计算完整自然周") from exc
    counts = repository.daily_submission_counts(db, start, end, department)
    report_dates = [start + timedelta(days=offset) for offset in range((end - start).days + 1)]
    return EmployeeReportSummary(
        period_start=start,
        period_end=end,
        department=report_scope_label(department),
        submitted_employee_days=sum(counts.values()),
        days=[
            DailySubmissionCount(report_date=report_date, submitted_employees=counts.get(report_date, 0))
            for report_date in report_dates
        ],
    )


def formal_employee_report(
    db: Session, principal: EmployeePrincipal, request: FormalReportRequest,
) -> FormalEmployeeReport:
    require_permission(principal, "reports:formal:generate")
    period = "day" if request.report_kind == "daily" else "week"
    statistics = employee_report_summary(db, principal, request.anchor, period)
    payload = _report_payload(db, statistics, _report_department(db, principal))
    # The workflow is remote. Release the database snapshot before waiting for it.
    db.rollback()
    if statistics.submitted_employee_days:
        sections = formal_dify.generate_summary(request.report_kind, payload)
    else:
        sections = FormalReportSections(
            work_summary=_NO_RECORDS,
            key_progress_summary=_NO_RECORDS,
            risk_summary=_NO_RECORDS,
            next_work_suggestions=_NO_RECORDS,
        )
    return FormalEmployeeReport(report_kind=request.report_kind, statistics=statistics, sections=sections)


def _report_payload(db: Session, statistics: EmployeeReportSummary, scope: str | int | None) -> str:
    header = json.dumps({
        "scope": {"department": statistics.department},
        "period": {"start": statistics.period_start.isoformat(), "end": statistics.period_end.isoformat()},
        "statistics": statistics.model_dump(mode="json"),
    }, ensure_ascii=False, separators=(",", ":"))
    rows = []
    size = len(header) + len(',"employees":[]')
    with closing(repository.formal_report_rows(
        db, statistics.period_start, statistics.period_end, scope
    )) as reports:
        for row in reports:
            record = {**row, "report_date": row["report_date"].isoformat()}
            entry = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
            size += len(entry) + bool(rows)
            if size > _MAX_PAYLOAD_CHARS:
                raise BusinessError(422, "报告内容超过工作流上限，请缩小报告时间或部门范围")
            rows.append(entry)
    return header[:-1] + ',"employees":[' + ",".join(rows) + "]}"


def operational_report(db: Session, principal: EmployeePrincipal, start: date, end: date):
    require_permission(principal, "reports:operations:read")
    department = _report_department(db, principal)
    if end < start or (end - start).days >= 366 or end == date.max:
        raise BusinessError(422, "请选择有效的起止日期，最长 366 天")
    leads, complaints = repository.operational_status_counts(db, start, end, department)
    return {"period_start": start, "period_end": end, "department": report_scope_label(department),
            "leads_by_status": leads, "complaints_by_status": complaints}
