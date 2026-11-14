from datetime import date, datetime, time, timedelta

from sqlalchemy import Date, Integer, case, column, func, select, table
from sqlalchemy.orm import Session

from app.modules.consultant.models import CrmLead
from app.modules.consultant.status_events import LeadStatusEvent
from app.modules.employee_report.models import EmployeeDailyReport, WeeklySubmission
from app.modules.feedback.models import student_feedback_ticket
from app.modules.organization.membership import managed_employees_query
from app.modules.student_admin.models import SysUser

from .repository import _submitted_reports



_history = table("report_status_history_start", column("id", Integer), column("start_day", Date))

def lead_history_since(db: Session):
    return db.scalar(select(_history.c.start_day).where(_history.c.id == 1))

def employee_filters(scope):
    filters = [SysUser.user_type == "employee", SysUser.status == "normal"]
    if isinstance(scope, int):
        filters.append(SysUser.id.in_(managed_employees_query(scope)))
    elif scope is not None:
        filters.append(SysUser.department == scope)
    return filters


def employee_board(db: Session, scope, start: date, end: date, department: str | None, status: str | None,
                   offset: int, limit: int, weekly: bool = False):
    report = EmployeeDailyReport
    submitted = _submitted_reports(start, end, scope, report.employee_id,
                                   func.count(func.distinct(report.report_date)).label("days"),
                                   func.max(report.create_time).label("submitted_at")).group_by(report.employee_id).subquery()
    if weekly:
        weekly_report = WeeklySubmission
        submitted = select(weekly_report.employee_id, case((weekly_report.employee_id.is_not(None), 1), else_=0).label("days"),
                           weekly_report.submitted_at).where(weekly_report.week_start == start).subquery()
    population = (
        select(SysUser.id.label("employee_id"), SysUser.real_name.label("name"), SysUser.department,
               func.coalesce(submitted.c.days, 0).label("report_days"), submitted.c.submitted_at)
        .outerjoin(submitted, submitted.c.employee_id == SysUser.id)
        .where(*employee_filters(scope))
    )
    if department is not None:
        population = population.where(SysUser.department == department)
    base = population.subquery()
    breakdown = db.execute(
        select(base.c.department, func.count().label("expected"),
               func.sum(case((base.c.report_days > 0, 1), else_=0)).label("submitted"))
        .group_by(base.c.department).order_by(base.c.department)
    ).mappings()
    departments = [dict(row) for row in breakdown]
    query = select(base).order_by(base.c.name, base.c.employee_id)
    if status is not None:
        query = query.where(base.c.report_days > 0 if status == "submitted" else base.c.report_days == 0)
    rows = [dict(row) for row in db.execute(query.offset(offset).limit(limit + 1)).mappings()]
    return departments, rows


def employee_detail(db: Session, scope, start: date, end: date, employee_id: int, weekly: bool = False):
    employee = db.execute(select(SysUser.id, SysUser.real_name, SysUser.department)
                          .where(*employee_filters(scope), SysUser.id == employee_id)).mappings().first()
    if employee is None:
        return None
    report = EmployeeDailyReport
    latest = _submitted_reports(start, end, scope, func.max(report.id)).where(
        report.employee_id == employee_id).group_by(report.report_date)
    rows = db.execute(select(report.id, report.report_date, report.content, report.key_progress, report.risks,
                             report.next_plan, report.create_time)
                      .where(report.id.in_(latest)).order_by(report.report_date.desc())).mappings()
    history = [dict(row) for row in rows]
    weekly_row = db.get(WeeklySubmission, (employee_id, start)) if weekly else None
    return {**employee, "reports": history, "weekly_report": (
        {key: getattr(weekly_row, key) for key in ("week_start", "content", "key_progress", "risks", "next_plan", "submitted_at")}
        if weekly_row else None
    )}


def scoped(query, staff_id, scope):
    if scope is None:
        return query
    return query.join(SysUser, SysUser.id == staff_id).where(*employee_filters(scope))


def bounds(start: date, end: date):
    return datetime.combine(start, time.min), datetime.combine(end + timedelta(days=1), time.min)


def lead_dashboard(db: Session, scope, start: date, end: date, metric: str | None, offset: int, limit: int):
    lead, event = CrmLead, LeadStatusEvent
    begin, finish = bounds(start, end)
    new = [lead.create_time >= begin, lead.create_time < finish]
    event_time = [event.occurred_at >= begin, event.occurred_at < finish]
    counts = dict(db.execute(scoped(select(lead.status, func.count()).where(*new).group_by(lead.status),
                                    lead.owner_employee_id, scope)).all())
    status_events = scoped(select(event.status, func.count())
                           .join(lead, lead.id == event.lead_id).where(*event_time)
                           .group_by(event.status), lead.owner_employee_id, scope)
    transitions = dict(db.execute(status_events).all())
    reason = func.coalesce(event.reason, "未填写")
    reasons = dict(db.execute(scoped(select(reason, func.count()).join(lead, lead.id == event.lead_id)
                                    .where(*event_time, event.status == "lost").group_by(reason),
                                    lead.owner_employee_id, scope)).all())
    # Department labels describe the current owning staff; the scope stays tied to live BASE membership.
    by_department = select(SysUser.department, func.count()).select_from(lead).outerjoin(
        SysUser, SysUser.id == lead.owner_employee_id).where(*new).group_by(SysUser.department)
    event_departments = select(SysUser.department, event.status, func.count()).select_from(event).join(
        lead, lead.id == event.lead_id).outerjoin(SysUser, SysUser.id == lead.owner_employee_id).where(
        *event_time).group_by(SysUser.department, event.status)
    if scope is not None:
        by_department = by_department.where(*employee_filters(scope))
        event_departments = event_departments.where(*employee_filters(scope))
    departments = {name: {"department": name, "new": count, "signed": 0, "lost": 0}
                   for name, count in db.execute(by_department)}
    for name, kind, count in db.execute(event_departments):
        departments.setdefault(name, {"department": name, "new": 0, "signed": 0, "lost": 0})[kind] = count
    rows = []
    if metric == "new":
        query = select(lead.id, lead.customer_name, lead.status, lead.create_time.label("occurred_at"),
                       lead.lost_reason.label("reason")).where(*new).order_by(lead.create_time.desc(), lead.id.desc())
    elif metric:
        query = select(lead.id, lead.customer_name, event.status, event.occurred_at, event.reason).select_from(event).join(
            lead, lead.id == event.lead_id).where(*event_time, event.status == metric).order_by(
            event.occurred_at.desc(), event.id.desc())
    if metric:
        rows = [dict(row) for row in db.execute(scoped(query, lead.owner_employee_id, scope)
                                               .offset(offset).limit(limit + 1)).mappings()]
    return {"leads_by_status": counts, "transitions": transitions, "lost_reasons": reasons,
            "departments": list(departments.values()), "items": rows[:limit], "has_more": len(rows) > limit}


def complaint_dashboard(db: Session, scope, start: date, end: date, as_of: datetime,
                        metric: str | None, offset: int, limit: int):
    ticket = student_feedback_ticket.c
    begin, finish = bounds(start, end)
    within = [ticket.create_time >= begin, ticket.create_time < finish]
    open_items = [ticket.status.in_(("pending", "processing")), ticket.create_time < as_of]
    category = func.coalesce(ticket.category, "未分类")
    def grouped(col, *filters):
        query = select(col, func.count()).where(ticket.ticket_type == "complaint", *filters).group_by(col)
        return dict(db.execute(scoped(query, ticket.assignee_id, scope)).all())

    backlog = {}
    for name, low, high in (("0–2 天", 0, 3), ("3–6 天", 3, 7), ("7–13 天", 7, 14), ("14 天以上", 14, None)):
        criteria = [*open_items, ticket.create_time <= as_of - timedelta(days=low)]
        if high is not None:
            criteria.append(ticket.create_time > as_of - timedelta(days=high))
        count = select(func.count()).select_from(student_feedback_ticket).where(
            ticket.ticket_type == "complaint", *criteria)
        backlog[name] = db.scalar(scoped(count, ticket.assignee_id, scope))
    rows = []
    if metric:
        filters = within if metric == "new" else open_items
        query = select(ticket.id, ticket.title, ticket.category, ticket.status, ticket.priority,
                       ticket.satisfaction, ticket.create_time).where(ticket.ticket_type == "complaint", *filters)
        rows = [dict(row) for row in db.execute(scoped(query, ticket.assignee_id, scope)
                                               .order_by(ticket.create_time.desc(), ticket.id.desc())
                                               .offset(offset).limit(limit + 1)).mappings()]
    return {"complaints_by_status": grouped(ticket.status, *within), "categories": grouped(category, *within),
            "satisfaction": grouped(ticket.satisfaction, *within, ticket.satisfaction.between(1, 5)),
            "backlog": backlog, "as_of": as_of, "items": rows[:limit], "has_more": len(rows) > limit}
