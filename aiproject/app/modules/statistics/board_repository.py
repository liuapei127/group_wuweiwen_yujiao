from datetime import date, datetime, time, timedelta

from sqlalchemy import Date, Integer, String, case, cast, column, func, select, table
from sqlalchemy.orm import Session

from app.modules.consultant.models import CrmFollowUp, CrmLead
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
    # The employee population below scopes both submission counts and roster entries.
    submitted = _submitted_reports(start, end, None, report.employee_id,
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


def _page(db, statement, offset, limit):
    rows = [dict(row) for row in db.execute(statement.offset(offset).limit(limit + 1)).mappings()]
    return {"items": rows[:limit], "has_more": len(rows) > limit}


def lead_dashboard(db: Session, scope, start: date, end: date, metric: str | None, offset: int, limit: int,
                   *, bucket: str | None = None, department: str | None = None, department_missing: bool = False):
    lead, event, follow = CrmLead, LeadStatusEvent, CrmFollowUp
    begin, finish = bounds(start, end)
    population = select(
        lead.id, lead.customer_name, lead.status, lead.create_time, lead.lost_reason,
        func.coalesce(func.nullif(func.trim(lead.source_channel), ""), "未填写").label("channel"),
        func.nullif(func.trim(SysUser.department), "").label("department"),
    ).outerjoin(SysUser, SysUser.id == lead.owner_employee_id)
    if scope is not None:
        population = population.where(*employee_filters(scope))
    population = population.subquery()
    customer = population.c
    new = [customer.create_time >= begin, customer.create_time < finish]
    event_time = [event.occurred_at >= begin, event.occurred_at < finish, event.status.in_(("signed", "lost"))]
    follow_time = [follow.create_time >= begin, follow.create_time < finish]
    reason = func.coalesce(func.nullif(func.trim(event.reason), ""), "未填写")
    method = func.coalesce(cast(follow.follow_type, String), "未填写")
    events = population.join(event, customer.id == event.lead_id)
    followups = population.join(follow, customer.id == follow.lead_id)
    counts = dict(db.execute(select(customer.status, func.count()).where(*new).group_by(customer.status)).all())
    transitions = dict(db.execute(select(event.status, func.count()).select_from(events)
                                  .where(*event_time).group_by(event.status)).all())
    reasons = dict(db.execute(select(reason, func.count()).select_from(events).where(
        *event_time, event.status == "lost").group_by(reason)).all())
    channels = dict(db.execute(select(customer.channel, func.count()).where(*new).group_by(customer.channel)).all())
    methods = dict(db.execute(select(method, func.count()).select_from(followups).where(*follow_time).group_by(method)).all())
    by_department = select(customer.department, func.count()).where(*new).group_by(customer.department)
    event_departments = select(customer.department, event.status, func.count()).select_from(events).where(
        *event_time).group_by(customer.department, event.status)
    departments = {name: {"department": name, "new": count, "signed": 0, "lost": 0}
                   for name, count in db.execute(by_department)}
    for name, kind, count in db.execute(event_departments):
        departments.setdefault(name, {"department": name, "new": 0, "signed": 0, "lost": 0})[kind] = count

    page = {"items": [], "has_more": False}
    if metric:
        filters = []
        if department_missing:
            filters.append(customer.department.is_(None))
        elif department is not None:
            filters.append(customer.department == department)
        if metric == "follow_up":
            query = select(customer.id, customer.customer_name, customer.status, follow.id.label("record_id"),
                           follow.create_time.label("occurred_at"), method.label("follow_type")).select_from(
                followups).where(*filters, *follow_time, method == bucket).order_by(
                follow.create_time.desc(), follow.id.desc())
        elif metric in ("signed", "lost"):
            query = select(customer.id, customer.customer_name, event.status, event.id.label("record_id"),
                           event.occurred_at, event.reason).select_from(events).where(
                *filters, *event_time, event.status == metric)
            if bucket is not None:
                query = query.where(reason == bucket)
            query = query.order_by(event.occurred_at.desc(), event.id.desc())
        else:
            query = select(customer.id, customer.customer_name, customer.status, customer.channel.label("source_channel"),
                           customer.create_time.label("occurred_at"), customer.lost_reason.label("reason")).where(*filters, *new)
            if metric == "status":
                query = query.where(customer.status == bucket)
            elif metric == "channel":
                query = query.where(customer.channel == bucket)
            query = query.order_by(customer.create_time.desc(), customer.id.desc())
        page = _page(db, query, offset, limit)
    return {"leads_by_status": counts, "transitions": transitions, "lost_reasons": reasons,
            "follow_ups": methods, "source_channels": channels,
            "departments": sorted(departments.values(), key=lambda row: (row["department"] is None, row["department"] or "")),
            **page}


BACKLOG_BANDS = {"0–2 天": (0, 3), "3–6 天": (3, 7), "7–13 天": (7, 14), "14 天以上": (14, None)}


def complaint_dashboard(db: Session, scope, start: date, end: date, as_of: datetime,
                        metric: str | None, offset: int, limit: int, *, bucket: str | None = None,
                        comparison_periods: dict[str, tuple[date, date]] | None = None):
    ticket = student_feedback_ticket.c

    def within(first, last):
        begin, finish = bounds(first, last)
        return ticket.create_time >= begin, ticket.create_time < finish

    open_items = [ticket.status.in_(("pending", "processing")), ticket.create_time <= as_of]
    category = func.coalesce(func.nullif(func.trim(ticket.category), ""), "未分类")

    def age_band(name):
        low, high = BACKLOG_BANDS[name]
        filters = [*open_items, ticket.create_time <= as_of - timedelta(days=low)]
        if high is not None:
            filters.append(ticket.create_time > as_of - timedelta(days=high))
        return filters

    def count(*filters):
        query = select(func.count()).select_from(student_feedback_ticket).where(ticket.ticket_type == "complaint", *filters)
        return db.scalar(scoped(query, ticket.assignee_id, scope))

    def grouped(col, *filters):
        query = select(col, func.count()).where(ticket.ticket_type == "complaint", *filters).group_by(col)
        return dict(db.execute(scoped(query, ticket.assignee_id, scope)).all())

    interval = within(start, end)
    statuses = grouped(ticket.status, *interval)
    total = sum(statuses.values())
    backlog = {name: count(*age_band(name)) for name in BACKLOG_BANDS}
    comparisons = {}
    for key, (first, last) in (comparison_periods or {}).items():
        baseline = count(*within(first, last))
        comparisons[key] = {"start": first, "end": last, "count": baseline, "change": total - baseline,
                            "percent": round((total - baseline) / baseline * 100, 1) if baseline else None}
    page = {"items": [], "has_more": False}
    if metric:
        filters = open_items if metric == "backlog" else list(interval)
        if metric == "backlog" and bucket is not None:
            filters = age_band(bucket)
        if metric == "status":
            filters.append(ticket.status == bucket)
        elif metric == "category":
            filters.append(category == bucket)
        elif metric == "satisfaction":
            filters.append(ticket.satisfaction == int(bucket))
        query = select(ticket.id, ticket.title, ticket.category, ticket.status, ticket.priority,
                       ticket.satisfaction, ticket.create_time).where(ticket.ticket_type == "complaint", *filters)
        page = _page(db, scoped(query, ticket.assignee_id, scope).order_by(ticket.create_time.desc(), ticket.id.desc()),
                     offset, limit)
    return {"complaints_by_status": statuses, "categories": grouped(category, *interval),
            "satisfaction": grouped(ticket.satisfaction, *interval, ticket.satisfaction.between(1, 5)),
            "backlog": backlog, "as_of": as_of, "comparisons": comparisons, **page}
