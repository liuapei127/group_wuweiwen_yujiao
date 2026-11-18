from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import success
from app.core.security import EmployeePrincipal, require_employee
from app.modules.profile.schemas import ScreeningInput

from . import intake_service as service
from .schemas import VisitorCallCreate, VisitorLeadCreate

router = APIRouter(prefix="/api/v1/consultant/visitor-intake", tags=["资源池"])
Database = Annotated[Session, Depends(get_db)]
Advisor = Annotated[EmployeePrincipal, Depends(require_employee)]
VisitorId = Annotated[int, Path(ge=1)]
SourceId = Annotated[int, Path(ge=1)]
Limit = Annotated[int, Query(ge=1, le=100)]
BeforeId = Annotated[int | None, Query(ge=1)]


@router.get("/pending")
def pending(db: Database, advisor: Advisor, after_id: Annotated[int, Query(ge=0)] = 0, limit: Limit = 50):
    return success(service.list_pending(db, advisor, after_id, limit))


@router.get("/assigned")
def assigned(db: Database, advisor: Advisor, after_id: Annotated[int, Query(ge=0)] = 0, limit: Limit = 50):
    return success(service.list_assigned(db, advisor, after_id, limit))


@router.get("/{visitor_id}")
def assigned_detail(visitor_id: VisitorId, db: Database, advisor: Advisor):
    return success(service.assigned_detail(db, visitor_id, advisor))


@router.post("/{visitor_id}/claim")
def claim(visitor_id: VisitorId, db: Database, advisor: Advisor):
    return success(service.claim(db, visitor_id, advisor))


@router.post("/{visitor_id}/calls")
def add_call(visitor_id: VisitorId, body: VisitorCallCreate, db: Database, advisor: Advisor):
    return success(service.add_call(db, visitor_id, advisor, body))


@router.get("/{visitor_id}/calls")
def list_calls(visitor_id: VisitorId, db: Database, advisor: Advisor, before_id: BeforeId = None, limit: Limit = 50):
    return success(service.list_calls(db, visitor_id, advisor, before_id, limit))


@router.get("/{visitor_id}/materials")
def list_materials(
    visitor_id: VisitorId, db: Database, advisor: Advisor, before_id: BeforeId = None, limit: Limit = 50,
):
    return success(service.list_materials(db, visitor_id, advisor, before_id, limit))


@router.get("/{visitor_id}/reservations")
def reservations(
    visitor_id: VisitorId, db: Database, advisor: Advisor, before_id: BeforeId = None, limit: Limit = 20,
):
    return success(service.list_reservations(db, visitor_id, advisor, before_id, limit))


@router.get("/{visitor_id}/materials/{source_id}")
def material_details(visitor_id: VisitorId, source_id: SourceId, db: Database, advisor: Advisor):
    return success(service.material_details(db, visitor_id, source_id, advisor))


@router.post("/{visitor_id}/materials/{source_id}/dify-preview")
def preview_material(visitor_id: VisitorId, source_id: SourceId, db: Database, advisor: Advisor):
    return success(service.preview_material(db, visitor_id, source_id, advisor))


@router.get("/{visitor_id}/materials/{source_id}/attachment")
def attachment(visitor_id: VisitorId, source_id: SourceId, db: Database, advisor: Advisor):
    filename, content = service.material_attachment(db, visitor_id, source_id, advisor)
    return Response(
        content, media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename*=UTF-8''" + quote(filename, safe=""),
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.post("/{visitor_id}/screening")
def supplement(
    visitor_id: VisitorId, body: ScreeningInput, db: Database, advisor: Advisor,
    source_id: Annotated[int | None, Query(ge=1)] = None,
):
    return success(service.supplement(db, visitor_id, advisor, body, source_id))


@router.get("/{visitor_id}/screening")
def screening(visitor_id: VisitorId, db: Database, advisor: Advisor):
    return success(service.manual_screening(db, visitor_id, advisor))


@router.post("/{visitor_id}/lead")
def create_lead(visitor_id: VisitorId, body: VisitorLeadCreate, db: Database, advisor: Advisor):
    return success(service.create_lead(db, visitor_id, advisor, body))
