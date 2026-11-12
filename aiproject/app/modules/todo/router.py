from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from typing import Literal
from app.core.security import EmployeePrincipal, require_employee
from app.core.database import get_db
from app.core.responses import success
from . import service
from .schemas import TodoInput, TodoUpdate

router = APIRouter(prefix="/api/v1/enterprise", tags=["企业助手扩展功能"])

@router.post('/todos')
def create_todo(body: TodoInput, db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(jsonable_encoder(service.create_todo(body=body, db=db, p=p)))

@router.get('/todos')
def list_todos(due_only: bool=False, limit: int=Query(50, ge=1, le=100), db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(jsonable_encoder(service.list_todos(due_only=due_only, limit=limit, db=db, p=p)))

@router.patch('/todos/{todo_id}')
def finish_todo(todo_id: int, body: TodoUpdate, db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(jsonable_encoder(service.finish_todo(todo_id=todo_id, body=body, db=db, p=p)))

@router.get('/notifications')
def notifications(limit: int=Query(50, ge=1, le=100), db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(jsonable_encoder(service.notifications(limit=limit, db=db, p=p)))

