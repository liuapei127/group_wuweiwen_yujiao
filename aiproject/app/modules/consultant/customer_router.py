from functools import partial
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import success
from app.core.security import EmployeePrincipal, require_employee
from app.modules.customer_service.mem0 import sync_profile
from app.modules.profile.service import MAX_UPLOAD_BYTES
from app.modules.profile.live import watch_profile
from app.modules.visitor.router import Principal as VisitorPrincipal

from . import customer_service as service
from .customer_schemas import ImportConfirm, ScreeningRequest, SharedFields, VerifiedIdentity, VersionedProfile


staff_router = APIRouter(prefix="/api/v1/consultant/leads", tags=["客户详情"])
visitor_router = APIRouter(prefix="/api/v1/visitors/customer-profile", tags=["官网客户资料"])
admin_router = APIRouter(prefix="/api/v1/enterprise/website-accounts", tags=["官网客户身份核验"])
Database = Annotated[Session, Depends(get_db)]
Staff = Annotated[EmployeePrincipal, Depends(require_employee)]
Upload = Annotated[UploadFile, File()]


@staff_router.get("/{lead_id}/profile")
def staff_profile(
    lead_id: int, db: Database, staff: Staff, response: Response,
    watch_version: Annotated[int | None, Query(ge=0)] = None,
):
    if watch_version is not None:
        return watch_profile(db, lambda: service.staff_profile_version(db, lead_id, staff), watch_version)
    response.headers["Cache-Control"] = "no-store"
    return success(service.staff_profile(db, lead_id, staff))


@staff_router.patch("/{lead_id}/profile")
def save_staff_profile(lead_id: int, body: VersionedProfile, db: Database, staff: Staff, background: BackgroundTasks):
    return success(service.save_staff_profile(db, lead_id, staff, body, on_saved=partial(background.add_task, sync_profile)))


@staff_router.post("/{lead_id}/readiness")
def draft_readiness(lead_id: int, body: SharedFields, db: Database, staff: Staff):
    return success(service.draft_readiness(db, lead_id, staff, body))


@staff_router.post("/{lead_id}/screening")
def run_screening(lead_id: int, body: ScreeningRequest, db: Database, staff: Staff):
    return success(service.run_screening(db, lead_id, staff, body.expected_version))


@staff_router.post("/{lead_id}/imports/preview")
async def preview_staff(lead_id: int, file: Upload, db: Database, staff: Staff):
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    return success(await run_in_threadpool(service.preview_staff, db, lead_id, staff, file.filename, content))


@staff_router.post("/{lead_id}/imports/confirm")
def confirm_staff(lead_id: int, body: ImportConfirm, db: Database, staff: Staff, background: BackgroundTasks):
    return success(service.confirm_staff(db, lead_id, staff, body, on_saved=partial(background.add_task, sync_profile)))


@staff_router.post("/{lead_id}/materials/{source_id}/imports/preview")
def preview_staff_material(lead_id: int, source_id: int, db: Database, staff: Staff):
    return success(service.preview_staff_material(db, lead_id, source_id, staff))


@visitor_router.get("")
def visitor_profile(
    db: Database, visitor: VisitorPrincipal, response: Response,
    watch_version: Annotated[int | None, Query(ge=0)] = None,
    include_pending: bool = False,
):
    if watch_version is not None:
        return watch_profile(db, lambda: service.visitor_profile_version(db, visitor, include_pending=include_pending), watch_version)
    response.headers["Cache-Control"] = "no-store"
    return success(service.visitor_profile(db, visitor, include_pending=include_pending))


@visitor_router.patch("")
def save_visitor_profile(body: VersionedProfile, db: Database, visitor: VisitorPrincipal, background: BackgroundTasks):
    return success(service.save_visitor_profile(db, visitor, body, on_saved=partial(background.add_task, sync_profile)))


@visitor_router.post("/imports/preview")
async def preview_visitor(file: Upload, db: Database, visitor: VisitorPrincipal):
    content = await file.read(MAX_UPLOAD_BYTES + 1)
    return success(await run_in_threadpool(service.preview_visitor, db, visitor, file.filename, content))


@visitor_router.post("/imports/confirm")
def confirm_visitor(body: ImportConfirm, db: Database, visitor: VisitorPrincipal, background: BackgroundTasks):
    return success(service.confirm_visitor(db, visitor, body, on_saved=partial(background.add_task, sync_profile)))


@admin_router.put("/customers/{lead_id}/identity")
def verify_identity(lead_id: int, body: VerifiedIdentity, db: Database, staff: Staff):
    return success(service.save_identity(db, lead_id, body, staff))
