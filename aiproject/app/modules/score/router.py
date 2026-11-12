from fastapi import APIRouter, Depends, Query
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session
from typing import Literal
from app.core.security import EmployeePrincipal, require_employee
from app.core.database import get_db
from app.core.responses import success
from . import service
from .schemas import ScoreCreate, ScoreCorrection

router = APIRouter(prefix="/api/v1/enterprise", tags=["企业助手扩展功能"])

@router.post('/scores')
def create_score(body: ScoreCreate, db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(jsonable_encoder(service.create_score(body=body, db=db, p=p)))

@router.get('/scores')
def list_scores(student_id: int=Query(gt=0), semester: str | None=None, limit: int=Query(50, ge=1, le=100), db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(jsonable_encoder(service.list_scores(student_id=student_id, semester=semester, limit=limit, db=db, p=p)))

@router.put('/scores/{score_id}')
def correct_score(score_id: int, body: ScoreCorrection, db: Session=Depends(get_db), p: EmployeePrincipal=Depends(require_employee)):
    return success(jsonable_encoder(service.correct_score(score_id=score_id, body=body, db=db, p=p)))


@router.get('/scores/{score_id}/history')
def score_history(score_id: int, limit: int = Query(50, ge=1, le=100), db: Session = Depends(get_db), p: EmployeePrincipal = Depends(require_employee)):
    return success(jsonable_encoder(service.score_history(score_id=score_id, limit=limit, db=db, p=p)))
