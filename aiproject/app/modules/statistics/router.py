from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query, Response
from pydantic import StringConstraints
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import success
from app.core.security import EmployeePrincipal, require_employee

from .schemas import FormalReportRequest, ScheduleKind, ScheduleWrite
from . import scheduled
from .pdf import render_report
from .periods import beijing_now
from .service import employee_report_summary, formal_employee_report, managed_employee_reports, operational_report

router = APIRouter(prefix="/api/v1/reporting", tags=["智能报告"])


@router.get("/employee-reports/summary")
def employee_summary(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[EmployeePrincipal, Depends(require_employee)],
    anchor: date | None = None,
    period: Literal["day", "week"] = "day",
):
    return success(employee_report_summary(db, principal, anchor or beijing_now().date(), period))


@router.get("/employee-reports/managed", summary="查询授权组织的已提交日报")
def managed_reports(
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[EmployeePrincipal, Depends(require_employee)],
    employee_name: Annotated[str | None, Query(), StringConstraints(strip_whitespace=True, min_length=1, max_length=64)] = None,
    anchor: date | None = None,
    period: Literal["day", "week"] = "day",
):
    return success(managed_employee_reports(db, principal, anchor or beijing_now().date(), period,
                                            employee_name))


@router.post("/employee-reports/formal-summary")
def formal_summary(
    request: FormalReportRequest,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[EmployeePrincipal, Depends(require_employee)],
):
    return success(formal_employee_report(db, principal, request))


@router.get("/operations")
def operations(
    start: date,
    end: date,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[EmployeePrincipal, Depends(require_employee)],
):
    return success(operational_report(db, principal, start, end))


@router.get("/schedules")
def report_schedules(db: Annotated[Session, Depends(get_db)], principal: Annotated[EmployeePrincipal, Depends(require_employee)]):
    return success(scheduled.preferences(db, principal))


@router.put("/schedules")
def configure_schedule(
    payload: ScheduleWrite, db: Annotated[Session, Depends(get_db)],
    principal: Annotated[EmployeePrincipal, Depends(require_employee)],
):
    return success(scheduled.configure(db, principal, payload))


@router.get("/archive")
def archive(
    db: Annotated[Session, Depends(get_db)], principal: Annotated[EmployeePrincipal, Depends(require_employee)],
    before_id: Annotated[int | None, Query(ge=1)] = None,
    kind: ScheduleKind | None = None,
    limit: Annotated[int, Query(ge=1, le=20)] = 20,
    shared: bool = False,
):
    return success(scheduled.archive(db, principal, before_id, kind=kind, limit=limit, shared=shared))


@router.get("/archive/{report_id}/pdf", response_class=Response, responses={
    200: {"content": {"application/pdf": {}}},
})
def archive_pdf(
    report_id: Annotated[int, Path(ge=1)],
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[EmployeePrincipal, Depends(require_employee)],
    shared: bool = False,
):
    report = scheduled.archived_report(db, principal, report_id, shared=shared)
    return Response(render_report(report), media_type="application/pdf", headers={
        "Content-Disposition": f'attachment; filename="report-{report_id}.pdf"',
        "Cache-Control": "no-store",
    })
