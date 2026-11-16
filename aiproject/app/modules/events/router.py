from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import success
from app.core.security import EmployeePrincipal, require_employee

from app.modules.visitor.router import Principal as VisitorPrincipal

from . import service
from .schemas import EventCreate, EventDetails, EventPublication

router = APIRouter(prefix="/api/v1/enterprise/events", tags=["活动管理"])
Database = Annotated[Session, Depends(get_db)]
Principal = Annotated[EmployeePrincipal, Depends(require_employee)]


@router.get("")
def list_events(
    db: Database, principal: Principal,
    before_id: Annotated[int | None, Query(ge=1)] = None, limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return success(service.list_staff_events(db, principal, before_id, limit))


@router.post("")
def create_event(payload: EventCreate, db: Database, principal: Principal):
    return success(service.create_event(db, payload, principal))


@router.put("/{event_id}")
def update_event(event_id: int, payload: EventDetails, db: Database, principal: Principal):
    return success(service.update_event(db, event_id, payload, principal))


@router.patch("/{event_id}/publication")
def set_publication(event_id: int, payload: EventPublication, db: Database, principal: Principal):
    return success(service.set_publication(db, event_id, payload.is_published, principal))


@router.delete("/{event_id}")
def delete_event(event_id: int, db: Database, principal: Principal):
    service.delete_event(db, event_id, principal)
    return success(None)


@router.get("/{event_id}/registrations")
def list_registrations(
    event_id: int, db: Database, principal: Principal,
    after_id: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=100),
):
    return success(service.list_staff_registrations(db, event_id, principal, after_id, limit))


@router.post("/{event_id}/registrations/{registration_id}/check-in")
def check_in(event_id: int, registration_id: int, db: Database, principal: Principal):
    return success(service.check_in(db, event_id, registration_id, principal))


visitor_router = APIRouter(prefix="/api/v1/visitor/events", tags=["官网活动"])


@visitor_router.get("")
def upcoming_events(
    db: Database, principal: VisitorPrincipal,
    offset: int = Query(0, ge=0, le=10000), limit: int = Query(50, ge=1, le=100),
):
    return success(service.upcoming_events(db, principal.visitor_id, offset, limit))


@visitor_router.get("/reservations")
def my_reservations(
    db: Database, principal: VisitorPrincipal,
    before_id: Annotated[int | None, Query(ge=1)] = None, limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return success(service.visitor_reservations(db, principal.visitor_id, before_id, limit))


@visitor_router.post("/{event_id}/reservation")
def reserve(event_id: int, db: Database, principal: VisitorPrincipal):
    return success(service.reserve(db, event_id, customer_id=principal.visitor_id))


@visitor_router.delete("/{event_id}/reservation")
def cancel(event_id: int, db: Database, principal: VisitorPrincipal):
    return success(service.cancel(db, event_id, customer_id=principal.visitor_id))
