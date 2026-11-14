from collections.abc import Iterator
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from app.modules.consultant.models import CrmLead
from app.modules.feedback.models import student_feedback_ticket
from app.modules.employee_report.models import EmployeeDailyReport
from app.modules.organization.membership import managed_employees_query
from app.modules.student_admin.models import SysUser


def active_manager_department(db: Session, employee_id: int) -> str | None:
    return db.scalar(select(SysUser.department).where(
        SysUser.id == employee_id,
        SysUser.user_type == "employee",
        SysUser.status == "normal",
    ))


def daily_submission_counts(
    db: Session, start: date, end: date, department: str | int | None
) -> dict[date, int]:
    reports = EmployeeDailyReport
    stmt = (
        _submitted_reports(start, end, department, reports.report_date, func.count(func.distinct(reports.employee_id)))
        .group_by(reports.report_date)
    )
    return {report_date: count for report_date, count in db.execute(stmt)}


def _submitted_reports(start: date, end: date, department: str | None, *columns):
    reports = EmployeeDailyReport
    stmt = (
        select(*columns)
        .select_from(reports)
        .join(SysUser, SysUser.id == reports.employee_id)
        .where(
            SysUser.user_type == "employee",
            SysUser.status == "normal",
            reports.status == "submitted",
            reports.report_date.between(start, end),
        )
    )
    if isinstance(department, int):
        stmt = stmt.where(SysUser.id.in_(managed_employees_query(department)))
    elif department is not None:
        stmt = stmt.where(SysUser.department == department)
    return stmt


def formal_report_rows(db: Session, start: date, end: date, department: str | None) -> Iterator[RowMapping]:
    reports = EmployeeDailyReport
    latest = _submitted_reports(start, end, department, func.max(reports.id)).group_by(
        reports.employee_id, reports.report_date
    )
    query = (
        select(
            SysUser.real_name.label("name"), SysUser.department, reports.report_date,
            reports.content, reports.key_progress, reports.risks, reports.next_plan,
        )
        .select_from(reports)
        .join(SysUser, SysUser.id == reports.employee_id)
        .where(reports.id.in_(latest))
        .order_by(reports.report_date, reports.employee_id)
        .execution_options(yield_per=32)
    )
    with db.execute(query) as result:
        yield from result.mappings()


def operational_status_counts(db: Session, start: date, end: date, department: str | None):
    from datetime import datetime, time, timedelta

    start_at = datetime.combine(start, time.min)
    end_at = datetime.combine(end + timedelta(days=1), time.min)
    tickets = student_feedback_ticket
    sources = (
        (CrmLead.__table__, CrmLead.__table__.c.owner_employee_id),
        (tickets, tickets.c.assignee_id),
    )
    counts = []
    for source, staff_id in sources:
        stmt = select(source.c.status, func.count()).select_from(source).where(
            source.c.create_time >= start_at, source.c.create_time < end_at,
        )
        if source is tickets:
            stmt = stmt.where(tickets.c.ticket_type == "complaint")
        if department is not None:
            stmt = stmt.join(SysUser, SysUser.id == staff_id).where(
                (SysUser.id.in_(managed_employees_query(department)) if isinstance(department, int)
                 else SysUser.department == department), SysUser.user_type == "employee",
                SysUser.status == "normal",
            )
        counts.append({status: count for status, count in db.execute(stmt.group_by(source.c.status))})
    return counts[0], counts[1]
