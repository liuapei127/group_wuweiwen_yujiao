from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from typing import Literal
from app.core.security import EmployeePrincipal, require_employee
from app.core.database import get_db
from app.core.responses import success
from . import service
from .schemas import TicketRouting, TicketUpdate

router = APIRouter(prefix="/api/v1/enterprise", tags=["企业助手扩展功能"])


@router.get("/ticket-routing")
def routing_queue(db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(service.routing_queue(db, p))


@router.put("/ticket-routing/{ticket_id}")
def route_ticket(ticket_id: int, body: TicketRouting, db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(service.route_ticket(db, p, ticket_id, body))


@router.get("/tickets/{ticket_id}/history")
def history(ticket_id: int, db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(service.ticket_history(db, p, ticket_id))

@router.get('/tickets')
def list_tickets(status: Literal['pending', 'processing', 'resolved', 'closed'] | None=None, limit: int=Query(50, ge=1, le=100), db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(jsonable_encoder(service.list_tickets(status=status, limit=limit, db=db, p=p)))

@router.get('/tickets/{ticket_id}')
def ticket_detail(ticket_id: int, db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(jsonable_encoder(service.ticket_detail(ticket_id=ticket_id, db=db, p=p)))

@router.patch('/tickets/{ticket_id}')
def process_ticket(ticket_id: int, body: TicketUpdate, db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(jsonable_encoder(service.process_ticket(ticket_id=ticket_id, body=body, db=db, p=p)))

