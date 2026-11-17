from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.modules.customer_service.mem0 import sync_profile
from app.core.responses import success
from app.core.security import EmployeePrincipal, require_employee

from app.modules.visitor.router import Principal as VisitorPrincipal

from . import service
from .models import SourceType
from .schemas import ScreeningInput

router = APIRouter(prefix="/api/v1/profile", tags=["客户研判"])
Database = Annotated[Session, Depends(get_db)]
Principal = Annotated[EmployeePrincipal, Depends(require_employee)]


@router.post("/upload")
async def upload(
    db: Database,
    principal: Principal,
    source_type: Annotated[SourceType, Form()],
    raw_content: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
):
    content = await file.read(service.MAX_UPLOAD_BYTES + 1) if file is not None else None
    result = await run_in_threadpool(
        service.upload_source, db, principal.employee_id, source_type, raw_content, file.filename if file else None, content,
    )
    return success(result)


@router.post("/{source_id}/analyze")
def analyze(source_id: int, db: Database, principal: Principal, update: ScreeningInput | None = None):
    return success(service.request_analysis(db, source_id, principal.employee_id, update or ScreeningInput()))


@router.get("")
def advisor_sources(
    db: Database, principal: Principal, before_id: Annotated[int | None, Query(ge=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return success(service.list_advisor_sources(db, principal.employee_id, before_id, limit))


@router.post("/{source_id}/dify-preview")
def advisor_preview(source_id: int, db: Database, principal: Principal):
    return success(service.preview_advisor_source(db, source_id, principal.employee_id))


@router.get("/{source_id}")
def query(source_id: int, db: Database, principal: Principal):
    return success(service.get_judgment(db, source_id, principal.employee_id))


visitor_router = APIRouter(prefix="/api/v1/visitor/materials", tags=["官网材料"])


@visitor_router.post("", status_code=201)
async def submit_material(
    db: Database, principal: VisitorPrincipal, background: BackgroundTasks,
    raw_content: Annotated[str | None, Form()] = None,
    file: Annotated[UploadFile | None, File()] = None,
):
    content = await file.read(service.MAX_UPLOAD_BYTES + 1) if file is not None else None
    result = await run_in_threadpool(
        service.submit_visitor_material, db, principal.visitor_id,
        raw_content, file.filename if file is not None else None, content,
    )
    background.add_task(sync_profile, db.get_bind(), principal.visitor_id)
    return success(result)


@visitor_router.get("")
def list_materials(
    db: Database, principal: VisitorPrincipal,
    before_id: Annotated[int | None, Query(ge=1)] = None, limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return success(service.visitor_materials(db, principal.visitor_id, before_id, limit))


@visitor_router.get("/{source_id}")
def material_progress(source_id: int, db: Database, principal: VisitorPrincipal):
    return success(service.visitor_material(db, principal.visitor_id, source_id))
