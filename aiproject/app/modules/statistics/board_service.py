from calendar import monthrange
import json
from datetime import date, timedelta
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.security.authorization import require_permission

from . import board_repository as repo, formal_dify, scheduled_repository
from .periods import beijing_now
from .service import _period_bounds, _report_department, report_scope_label


def employee_board(db: Session, principal, anchor, period, department, status, offset, limit):
    require_permission(principal, "reports:summary:read")
    scope = _report_department(db, principal)
    start, end = _period_bounds(anchor, period)
    departments, rows = repo.employee_board(db, scope, start, end, department, status, offset, limit, weekly=period == "week")
    for row in departments:
        row["missing"] = row["expected"] - row["submitted"]
    expected = sum(row["expected"] for row in departments)
    submitted = sum(row["submitted"] for row in departments)
    return {"period_start": start, "period_end": end, "expected": expected, "submitted": submitted,
            "missing": expected - submitted, "departments": departments, "items": rows[:limit],
            "has_more": len(rows) > limit}


def employee_detail(db, principal, anchor, period, employee_id):
    require_permission(principal, "reports:summary:read")
    scope = _report_department(db, principal)
    start, end = _period_bounds(anchor, period)
    detail = repo.employee_detail(db, scope, start, end, employee_id, weekly=period == "week")
    if detail is None:
        raise BusinessError(404, "员工不存在或不在你的报表范围")
    return detail


def summarize_employee(db, principal, anchor, period, employee_id):
    require_permission(principal, "reports:formal:generate")
    detail = employee_detail(db, principal, anchor, period, employee_id)
    if period == "week":
        reports = [detail["weekly_report"]] if detail["weekly_report"] else []
    else:
        reports = detail["reports"]
    if not reports:
        raise BusinessError(422, "该员工在所选周期尚未提交报告")
    start, end = _period_bounds(anchor, period)
    payload = json.dumps({
        "period": {"start": start.isoformat(), "end": end.isoformat()},
        "employees": [{
            "name": detail["real_name"],
            "report_date": (row.get("report_date") or row["week_start"]).isoformat(),
            **{key: row.get(key) for key in ("content", "key_progress", "risks", "next_plan")},
        } for row in reports],
    }, ensure_ascii=False, separators=(",", ":"))
    if len(payload) > 50_000:
        raise BusinessError(422, "报告内容超过工作流上限，请缩小报告范围")
    db.rollback()
    sections = formal_dify.generate_summary("weekly" if period == "week" else "daily", payload)
    current = employee_detail(db, principal, anchor, period, employee_id)
    source = "weekly_report" if period == "week" else "reports"
    if current[source] != detail[source]:
        raise BusinessError(409, "报告已更新，请刷新原文后重新生成总结")
    return {"sections": sections}


def _complaint_comparison_periods(start, end):
    periods = {}
    days = (end - start).days + 1
    if start.day == 1 and start.month == end.month and start.year == end.year and end.day == monthrange(end.year, end.month)[1]:
        if start > date.min:
            previous_end = start - timedelta(days=1)
            periods["previous"] = (previous_end.replace(day=1), previous_end)
    elif (start - date.min).days >= days:
        periods["previous"] = (start - timedelta(days=days), start - timedelta(days=1))
    if start.year > 1:
        def last_year(day):
            year = day.year - 1
            return day.replace(year=year, day=min(day.day, monthrange(year, day.month)[1]))
        periods["year_ago"] = (last_year(start), last_year(end))
    return periods


def operations(db, principal, kind, start, end, metric=None, offset=0, limit=30, *, bucket=None,
               department=None, department_missing=False):
    require_permission(principal, "reports:operations:read")
    scope = _report_department(db, principal)
    if end < start or (end - start).days >= 366 or end == date.max:
        raise BusinessError(422, "请选择有效的日期范围，最长 366 天")
    if kind == "customers":
        if ((metric in ("status", "channel", "follow_up") and not bucket)
                or (bucket is not None and metric not in ("status", "channel", "follow_up", "lost"))
                or (metric == "status" and bucket not in ("new", "contacting", "qualified", "signed", "lost"))
                or (metric == "follow_up" and bucket not in ("phone", "wechat", "meeting", "email", "other", "未填写"))
                or (department is not None and department_missing)):
            raise BusinessError(422, "请选择有效的客户明细筛选条件")
        data = repo.lead_dashboard(db, scope, start, end, metric, offset, limit,
                                   bucket=bucket, department=department, department_missing=department_missing)
        data["status_history_since"] = repo.lead_history_since(db)
    else:
        if ((metric in ("status", "category", "satisfaction") and not bucket)
                or (bucket is not None and metric not in ("status", "category", "satisfaction", "backlog"))
                or (metric == "status" and bucket not in ("pending", "processing", "resolved", "closed"))
                or (metric == "satisfaction" and bucket not in ("1", "2", "3", "4", "5"))
                or (metric == "backlog" and bucket is not None and bucket not in repo.BACKLOG_BANDS)):
            raise BusinessError(422, "请选择有效的投诉明细筛选条件")
        data = repo.complaint_dashboard(db, scope, start, end, beijing_now(), metric, offset, limit,
                                        bucket=bucket, comparison_periods=_complaint_comparison_periods(start, end))
    return {"period_start": start, "period_end": end, "department": report_scope_label(scope), **data}


class OperationArchiveRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: date
    end: date
    include_ai: bool = False


def archive_operations(db, principal, kind, request: OperationArchiveRequest):
    from fastapi.encoders import jsonable_encoder
    from .report_ai import suggest

    data = operations(db, principal, kind, request.start, request.end)
    scope = _report_department(db, principal)
    from app.modules.organization.membership import managed_employees_query
    department_members = sorted(db.scalars(managed_employees_query(scope))) if isinstance(scope, int) else None
    data.pop("items", None)
    data.pop("has_more", None)
    db.rollback()
    if kind == "complaints" and request.include_ai:
        data["ai_summary"] = suggest("投诉", {
            key: data[key] for key in ("complaints_by_status", "satisfaction", "backlog")
        })
    stats = jsonable_encoder(data)
    report_type, title = ("complaint_weekly", "投诉处理周报") if kind == "complaints" else ("customer_ops", "客户经营报告")
    archive_id = scheduled_repository.record_report(
        db, principal.employee_id, report_type, title,
        {"period_start": stats["period_start"], "period_end": stats["period_end"], "scope_version": 1,
         "department": stats["department"], "department_members": department_members, "statistics": stats},
        beijing_now(),
    )
    db.commit()
    return {"archive_id": archive_id, **stats}
