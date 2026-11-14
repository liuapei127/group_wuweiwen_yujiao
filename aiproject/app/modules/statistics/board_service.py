from datetime import date
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.core.security.authorization import require_permission

from . import board_repository as repo, scheduled_repository
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


def operations(db, principal, kind, start, end, metric=None, offset=0, limit=30):
    require_permission(principal, "reports:operations:read")
    scope = _report_department(db, principal)
    if end < start or (end - start).days >= 366 or end == date.max:
        raise BusinessError(422, "请选择有效的日期范围，最长 366 天")
    now = beijing_now()
    if kind == "customers":
        data = repo.lead_dashboard(db, scope, start, end, metric, offset, limit)
        data["status_history_since"] = repo.lead_history_since(db)
    else:
        data = repo.complaint_dashboard(db, scope, start, end, now, metric, offset, limit)
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
