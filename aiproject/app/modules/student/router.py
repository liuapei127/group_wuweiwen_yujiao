from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.core.security import EmployeePrincipal, require_employee
from app.core.responses import success
from app.modules.customer_service.capacity import CsCapacityExceeded, get_cs_capacity
from app.modules.feedback import service as feedback
from app.modules.feedback.schemas import StudentComplaintCreate
from app.modules.student_admin.schemas import StudentLeaveCreate
from app.modules.student_admin.service import StudentAdminServiceLayer
from app.modules.visitor.router import Database, Principal
from sqlalchemy.orm import Session
from app.modules.visitor.service import VisitorPrincipal
from app.modules.visitor.repository import student_destination
from app.modules.visitor.service import website_student

from . import alerts, assistant_chat, assistant_dify, notifications, service
from .schemas import DeadlineWrite, ProgressWrite, StudentAssistantRequest
from .service import student_policies

_BEARER = HTTPBearer(auto_error=False)

router = APIRouter(prefix="/api/v1/student", tags=["官网学生服务"])
BeforeId = Annotated[int | None, Query(ge=1)]
Limit = Annotated[int, Query(ge=1, le=100)]


def _student_id(db: Session, principal: VisitorPrincipal, *, lock: bool = False) -> int:
    student_id = website_student(db, principal, lock=lock)
    if student_id is None:
        raise BusinessError(403, "当前官网账号未开通学生服务")
    return student_id


def _local_assistant(db: Session, principal: VisitorPrincipal, body: StudentAssistantRequest) -> dict:
    student_id = _student_id(db, principal, lock=False)
    db.rollback()
    history = [turn.model_dump() for turn in (body.history or [])]
    return assistant_chat.handle_chat(
        db,
        student_id=student_id,
        message=body.query,
        history=history,
        mock_country=body.mock_country,
    )


@router.post("/assistant/run")
async def student_assistant_run(body: StudentAssistantRequest, request: Request, db: Database, principal: Principal):
    """Always-local brain for the Dify thin shell. Do not call Dify from here."""

    def resolve() -> int:
        student_id = _student_id(db, principal, lock=False)
        db.rollback()
        return student_id

    student_id = await run_in_threadpool(resolve)
    client_ip = request.client.host if request.client else f"student:{student_id}"

    try:
        async with get_cs_capacity().slot(client_ip):
            return success(await run_in_threadpool(_local_assistant, db, principal, body))
    except CsCapacityExceeded as exc:
        raise BusinessError(429, exc.message) from exc


@router.post("/assistant")
async def student_assistant(
    body: StudentAssistantRequest,
    request: Request,
    db: Database,
    principal: Principal,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER)] = None,
):
    """Website entry: Dify shell when ``STU_DIFY_API_KEY`` is set, otherwise local brain."""

    def resolve() -> int:
        student_id = _student_id(db, principal, lock=False)
        db.rollback()
        return student_id

    student_id = await run_in_threadpool(resolve)
    client_ip = request.client.host if request.client else f"student:{student_id}"
    use_dify = bool(get_settings().stu_dify_api_key.get_secret_value().strip())

    try:
        async with get_cs_capacity().slot(client_ip):
            if use_dify:
                token = credentials.credentials if credentials else ""
                if not token:
                    raise BusinessError(401, "请先登录官网")
                history = [turn.model_dump() for turn in (body.history or [])]
                return success(
                    await assistant_dify.ask_dify(
                        query=body.query,
                        access_token=token,
                        history=history,
                        user_key=f"student_{student_id}",
                    )
                )
            return success(await run_in_threadpool(_local_assistant, db, principal, body))
    except CsCapacityExceeded as exc:
        raise BusinessError(429, exc.message) from exc


@router.get("/profile")
def profile(db: Database, principal: Principal):
    return success({"abroad_country": student_destination(db, _student_id(db, principal))})


@router.get("/notifications")
def notifications_inbox(db: Database, principal: Principal, before_id: BeforeId = None, limit: Limit = 20):
    return success(notifications.student_results(db, _student_id(db, principal), before_id, limit))


@router.get("/overseas-life")
def overseas_life(
    db: Database, principal: Principal, keyword: Annotated[str, Query(max_length=64)] = "",
    after_id: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=50)] = 12,
):
    return success(service.overseas_resources(db, _student_id(db, principal), keyword.strip(), after_id, limit))


@router.get("/policies")
def policies(db: Database, principal: Principal):
    return success(student_policies(db, _student_id(db, principal)))


@router.get("/deadlines")
def deadlines(
    db: Database, principal: Principal, upcoming: bool = True,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0, limit: Limit = 20,
):
    return success(service.academic_deadlines(
        db, _student_id(db, principal), offset=offset, limit=limit, upcoming=upcoming,
    ))


@router.post("/deadlines/{deadline_id}/complete")
def complete_deadline(deadline_id: int, db: Database, principal: Principal):
    return success(service.finish_deadline(db, _student_id(db, principal, lock=True), deadline_id))


@router.get("/application-progress")
def my_application_progress(db: Database, principal: Principal, before_id: BeforeId = None, limit: Limit = 20):
    return success(service.application_progress(db, _student_id(db, principal), before_id, limit))


@router.get("/leaves")
def leaves(db: Database, principal: Principal, before_id: BeforeId = None, limit: Limit = 20):
    return success(StudentAdminServiceLayer(db).student_leaves(_student_id(db, principal), before_id, limit))


@router.post("/leaves", status_code=201)
def submit_leave(payload: StudentLeaveCreate, db: Database, principal: Principal):
    return success(StudentAdminServiceLayer(db).submit_student_leave(_student_id(db, principal, lock=True), payload))


@router.get("/complaints")
def complaints(db: Database, principal: Principal, before_id: BeforeId = None, limit: Limit = 20):
    return success(feedback.student_complaints(db, _student_id(db, principal), before_id, limit))


@router.post("/complaints", status_code=201)
def submit_complaint(payload: StudentComplaintCreate, db: Database, principal: Principal):
    return success(feedback.submit_student_complaint(db, _student_id(db, principal, lock=True), payload))


staff_router = APIRouter(prefix="/api/v1/student-admin/application-progress", tags=["企业申请进度"])
Advisor = Annotated[EmployeePrincipal, Depends(require_employee)]


@staff_router.get("/students")
def eligible_students(db: Database, advisor: Advisor):
    return success(service.scoped_students(db, advisor, "applications:read"))


@staff_router.get("/{student_id}")
def staff_progress(student_id: int, db: Database, advisor: Advisor, before_id: BeforeId = None, limit: Limit = 20):
    return success(service.staff_progress(db, advisor, student_id, before_id, limit))


@staff_router.post("/{student_id}", status_code=201)
def create_progress(student_id: int, payload: ProgressWrite, db: Database, advisor: Advisor):
    return success(service.save_progress(db, advisor, student_id, payload))


@staff_router.put("/{student_id}/{progress_id}")
def update_progress(student_id: int, progress_id: int, payload: ProgressWrite, db: Database, advisor: Advisor):
    return success(service.save_progress(db, advisor, student_id, payload, progress_id))


academic_router = APIRouter(prefix="/api/v1/student-admin/academic-deadlines", tags=["企业考务"])


@academic_router.get("/students")
def academic_students(db: Database, advisor: Advisor):
    return success(service.scoped_students(db, advisor, "academics:read"))


@academic_router.get("/{student_id}")
def staff_deadlines(
    student_id: int, db: Database, advisor: Advisor, limit: Limit = 20,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
):
    return success(service.staff_deadlines(db, advisor, student_id, offset, limit))


@academic_router.post("/{student_id}", status_code=201)
def create_deadline(student_id: int, payload: DeadlineWrite, db: Database, advisor: Advisor):
    return success(service.save_deadline(db, advisor, student_id, payload))


@academic_router.put("/{student_id}/{deadline_id}")
def update_deadline(student_id: int, deadline_id: int, payload: DeadlineWrite, db: Database, advisor: Advisor):
    return success(service.save_deadline(db, advisor, student_id, payload, deadline_id=deadline_id))


alert_router = APIRouter(prefix="/api/v1/student-admin/psych-alerts", tags=["内部心理预警"])


@alert_router.get("")
def list_alerts(db: Database, advisor: Advisor, before_id: BeforeId = None, limit: Limit = 20):
    return success(alerts.list_alerts(db, advisor, before_id, limit))


@alert_router.get("/weekly")
def weekly_alerts(anchor: date, db: Database, advisor: Advisor):
    try:
        return success(alerts.weekly_alerts(db, advisor, anchor))
    except OverflowError as exc:
        raise BusinessError(422, "该日期无法计算完整自然周") from exc


@alert_router.post("", status_code=201)
def create_alert(payload: alerts.AlertCreate, db: Database, advisor: Advisor):
    return success(alerts.create_alert(db, advisor, payload))


@alert_router.get("/students")
def alert_students(db: Database, advisor: Advisor):
    return success(service.scoped_students(db, advisor, "student-alerts:read"))


@alert_router.put("/{alert_id}")
def follow_alert(alert_id: int, payload: alerts.AlertUpdate, db: Database, advisor: Advisor):
    return success(alerts.follow_alert(db, advisor, alert_id, payload))
