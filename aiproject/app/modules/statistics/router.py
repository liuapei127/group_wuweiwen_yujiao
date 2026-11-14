from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import success
from app.core.security import EmployeePrincipal, require_employee

from .schemas import FormalReportRequest, ScheduleWrite
from . import scheduled
from .service import employee_report_summary, formal_employee_report, operational_report

router = APIRouter(prefix="/api/v1/reporting", tags=["智能报告"])


@router.get("/employee-reports/summary")
def employee_summary(
    anchor: date,
    db: Annotated[Session, Depends(get_db)],
    principal: Annotated[EmployeePrincipal, Depends(require_employee)],
    period: Literal["day", "week"] = "day",
):
    return success(employee_report_summary(db, principal, anchor, period))


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
):
    return success(scheduled.archive(db, principal, before_id))
