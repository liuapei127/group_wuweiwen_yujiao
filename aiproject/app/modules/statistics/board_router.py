from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import success
from app.core.security import EmployeePrincipal, require_employee

from . import board_service as service, employee_conflicts, analysis, rules
from .periods import beijing_now

router = APIRouter(prefix="/api/v1/reporting", tags=["智报中心"])
DB = Annotated[Session, Depends(get_db)]
Staff = Annotated[EmployeePrincipal, Depends(require_employee)]
Offset = Annotated[int, Query(ge=0, le=100000)]
Limit = Annotated[int, Query(ge=1, le=100)]


@router.get("/rules")
def read_rules(db: DB, staff: Staff):
    return success(rules.get_rules(db, staff))


@router.put("/rules")
def save_rules(body: rules.RuleUpdate, db: DB, staff: Staff):
    return success(rules.update_rules(db, staff, body))


@router.get("/board/customers/analysis")
def customer_analysis(start: date, end: date, db: DB, staff: Staff):
    return success(analysis.customer_analysis(db, staff, start, end))


@router.get("/board/customers/intelligence")
def customer_intelligence(start: date, end: date, db: DB, staff: Staff):
    return success(analysis.customer_intelligence(db, staff, start, end))


@router.post("/board/customers/summary")
def customer_summary(body: service.OperationArchiveRequest, db: DB, staff: Staff):
    return success(analysis.customer_summary(db, staff, body.start, body.end))


@router.get("/board/projects/health")
def project_health(db: DB, staff: Staff):
    return success(analysis.project_health(db, staff))


@router.post("/board/complaints/{ticket_id}/classification")
def classify_complaint(ticket_id: Annotated[int, Path(ge=1)], db: DB, staff: Staff):
    return success(analysis.classify_complaint(db, staff, ticket_id))


@router.get("/board/complaints/analysis")
def complaint_analysis(start: date, end: date, db: DB, staff: Staff):
    return success(analysis.complaint_analysis(db, staff, start, end))


@router.get("/board/employees")
def employees(db: DB, staff: Staff, anchor: date | None = None, period: Literal["day", "week"] = "day",
              department: Annotated[str | None, Query(max_length=128)] = None,
              status: Literal["submitted", "missing"] | None = None, offset: Offset = 0, limit: Limit = 30):
    return success(service.employee_board(db, staff, anchor or beijing_now().date(), period,
                                          department, status, offset, limit))


@router.get("/board/employees/{employee_id}")
def employee(employee_id: Annotated[int, Path(ge=1)], db: DB, staff: Staff, anchor: date | None = None,
             period: Literal["day", "week"] = "day"):
    return success(service.employee_detail(db, staff, anchor or beijing_now().date(), period, employee_id))


@router.post("/board/employees/{employee_id}/summary")
def summarize_employee(employee_id: Annotated[int, Path(ge=1)], db: DB, staff: Staff, anchor: date,
                       period: Literal["day", "week"] = "day"):
    return success(service.summarize_employee(db, staff, anchor, period, employee_id))


@router.get("/board/customers")
def customers(start: date, end: date, db: DB, staff: Staff,
              metric: Literal["new", "signed", "lost", "status", "channel", "follow_up", "country", "education", "project"] | None = None,
              offset: Offset = 0, limit: Limit = 30,
              bucket: Annotated[str | None, Query(max_length=255)] = None,
              department: Annotated[str | None, Query(max_length=128)] = None, department_missing: bool = False):
    return success(service.operations(db, staff, "customers", start, end, metric, offset, limit,
                                      bucket=bucket, department=department, department_missing=department_missing))


@router.get("/board/complaints")
def complaints(start: date, end: date, db: DB, staff: Staff,
               metric: Literal["new", "backlog", "status", "category", "satisfaction"] | None = None,
               offset: Offset = 0, limit: Limit = 30, bucket: Annotated[str | None, Query(max_length=255)] = None):
    return success(service.operations(db, staff, "complaints", start, end, metric, offset, limit, bucket=bucket))


@router.post("/board/{kind}/archive", status_code=201)
def operation_archive(kind: Literal["customers", "complaints"], body: service.OperationArchiveRequest,
                      db: DB, staff: Staff):
    return success(service.archive_operations(db, staff, kind, body))


@router.get("/board/employees/{employee_id}/conflicts")
def findings(employee_id: Annotated[int, Path(ge=1)], anchor: date, db: DB, staff: Staff):
    return success(employee_conflicts.list_findings(db, staff, employee_id, anchor))


@router.post("/board/employees/{employee_id}/conflicts")
def scan_conflicts(employee_id: Annotated[int, Path(ge=1)], anchor: date, db: DB, staff: Staff):
    return success(employee_conflicts.scan(db, staff, employee_id, anchor))


@router.put("/board/conflicts/{conflict_id}")
def resolve_conflict(conflict_id: Annotated[int, Path(ge=1)], body: employee_conflicts.Resolution,
                     db: DB, staff: Staff):
    return success(employee_conflicts.resolve(db, staff, conflict_id, body))
