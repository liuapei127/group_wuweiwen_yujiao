from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from starlette.concurrency import run_in_threadpool

from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.core.security import EmployeePrincipal, require_employee
from app.core.responses import success
from app.core.responses.streaming import chat_response
from app.modules.customer_service.capacity import CsCapacityExceeded
from app.modules.feedback import service as feedback
from app.modules.feedback.schemas import StudentComplaintCreate
from app.modules.student_admin.schemas import StudentLeaveCreate
from app.modules.student_admin.service import StudentAdminServiceLayer
from app.modules.visitor.router import Database, Principal
from sqlalchemy.orm import Session
from app.modules.visitor.service import VisitorPrincipal
from app.modules.visitor.repository import student_destination
from app.modules.visitor.service import website_student

from . import alerts, assistant_chat, assistant_session, notifications, service
from .capacity import get_stu_capacity
from .idempotency import replay_cache
from .schemas import DeadlineBatch, DeadlineWrite, ProgressWrite, StudentAssistantConversationCreate, StudentAssistantRequest
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


def _run_local_turn(db: Session, principal: VisitorPrincipal, body: StudentAssistantRequest) -> dict:
    """Dify shell / legacy callers: optional client history, no session persistence required."""
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


@router.get("/assistant/conversations")
def assistant_conversations(db: Database, principal: Principal):
    return success(assistant_session.list_conversations(db, _student_id(db, principal)))


@router.post("/assistant/conversations", status_code=201)
def create_assistant_conversation(
    db: Database,
    principal: Principal,
    body: StudentAssistantConversationCreate = StudentAssistantConversationCreate(),
):
    return success(
        assistant_session.create_conversation(
            db, _student_id(db, principal), title=(body.title or "新对话")
        )
    )


@router.get("/assistant/conversations/{conversation_id}")
def assistant_conversation_detail(conversation_id: str, db: Database, principal: Principal):
    return success(
        assistant_session.conversation_detail(db, _student_id(db, principal), conversation_id)
    )


@router.post("/assistant/run")
async def student_assistant_run(body: StudentAssistantRequest, request: Request, db: Database, principal: Principal):
    """Always-local brain for the Dify thin shell. Do not call Dify from here."""

    def resolve() -> int:
        student_id = _student_id(db, principal, lock=False)
        db.rollback()
        return student_id

    student_id = await run_in_threadpool(resolve)
    # Dify 回调的源地址是容器 IP，按 IP 限流会变成全体学生共用一个桶；按学生计。
    bucket = f"student:{student_id}"
    cache = replay_cache()
    history = [turn.model_dump() for turn in (body.history or [])]
    key = cache.key(student_id, body.query, history, mock_country=body.mock_country)

    def run() -> dict:
        # Dify 失败重试会重复提交请假/投诉，同一轮请求只执行一次。
        payload, _ = cache.remember(key, lambda: _run_local_turn(db, principal, body))
        return payload

    try:
        # Dify 回调入口：外层 /assistant 已占用槽位，这里只查频率。
        async with get_stu_capacity().rate_only(bucket):
            return success(await run_in_threadpool(run))
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
    """Website entry with conversation records + mem0; optional Dify thin shell."""

    def resolve() -> int:
        student_id = _student_id(db, principal, lock=False)
        db.rollback()
        return student_id

    student_id = await run_in_threadpool(resolve)
    client_ip = request.client.host if request.client else f"student:{student_id}"
    use_dify = bool(get_settings().stu_dify_api_key.get_secret_value().strip())
    token = credentials.credentials if credentials else ""
    if use_dify and not token:
        raise BusinessError(401, "请先登录官网")

    async def run(on_text=None):
        try:
            async with get_stu_capacity().slot(client_ip):
                return await assistant_session.run_turn(
                    db, student_id=student_id, query=body.query, conversation_id=body.conversation_id,
                    access_token=token if use_dify else None, use_dify=use_dify,
                    mock_country=body.mock_country, **({"on_text": on_text} if on_text else {}),
                )
        except CsCapacityExceeded as exc:
            raise BusinessError(429, exc.message) from exc

    if "text/event-stream" in request.headers.get("accept", ""):
        return chat_response(run)
    return success(await run())


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


@router.post("/leaves/attachments", status_code=201)
def upload_leave_proof(db: Database, principal: Principal, file: UploadFile = File(...)):
    from app.modules.student_admin.attachments import MAX_PROOF_BYTES, upload
    student_id = _student_id(db, principal, lock=True)
    return success(upload(db, student_id, file.filename, file.file.read(MAX_PROOF_BYTES + 1)))


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


@academic_router.post("/classes/{class_id}/batch", status_code=201)
def class_deadlines(class_id: int, payload: DeadlineBatch, db: Database, advisor: Advisor):
    return success(service.class_deadlines(db, advisor, class_id, payload))


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
def list_alerts(db: Database, advisor: Advisor, before_id: BeforeId = None, limit: Limit = 20,
                student_id: Annotated[int | None, Query(gt=0)] = None):
    return success(alerts.list_alerts(db, advisor, before_id, limit, student_id))


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
