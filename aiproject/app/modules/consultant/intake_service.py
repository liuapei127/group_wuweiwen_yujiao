from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.security import EmployeePrincipal
from app.core.security.authorization import require_permission
from app.core.security.credentials import utc_now
from app.modules.profile import repository as materials, service as profiling
from app.modules.profile.dify_workflow import ReviewPreview, review_text
from app.modules.profile.extract import extract_text
from app.modules.profile.models import CustomerSource, ParseStatus, SourceType
from app.modules.profile.schemas import ScreeningInput
from app.modules.visitor.models import VisitorAccount
from app.shared.utils.time_util import now_naive

from . import intake_repository as repository
from .models import CrmFollowUp, CrmLead, VisitorCall, VisitorIntake
from .schemas import ClaimedVisitor, LeadOut, VisitorCallCreate, VisitorCallOut, VisitorLeadCreate, VisitorQueueEntry


def list_pending(db: Session, principal: EmployeePrincipal, after_id: int, limit: int):
    require_permission(principal, "visitor-intake:read")
    return [VisitorQueueEntry.model_validate(row) for row in repository.pending(db, after_id, limit)]


def list_assigned(db: Session, principal: EmployeePrincipal, after_id: int, limit: int):
    require_permission(principal, "visitor-intake:read")
    return [_visitor_details(account, case) for account, case in
            repository.assigned(db, principal.employee_id, after_id, limit)]


def assigned_detail(db: Session, visitor_id: int, principal: EmployeePrincipal) -> ClaimedVisitor:
    require_permission(principal, "visitor-intake:read")
    case = _owned_case(db, visitor_id, principal.employee_id)
    account = db.get(VisitorAccount, visitor_id)
    if account is None:
        raise BusinessError(404, "游客不存在")
    return _visitor_details(account, case)


def claim(db: Session, visitor_id: int, principal: EmployeePrincipal) -> ClaimedVisitor:
    require_permission(principal, "visitor-intake:write")
    require_permission(principal, "crm:write")
    try:
        account = repository.lock_visitor(db, visitor_id)
        if account is None:
            raise BusinessError(404, "游客不存在")
        case = repository.intake(db, visitor_id, lock=True)
        if case is None:
            case = VisitorIntake(visitor_id=visitor_id, advisor_id=principal.employee_id, claimed_at=utc_now())
            db.add(case)
        elif case.advisor_id != principal.employee_id:
            raise BusinessError(409, "游客已被其他顾问认领")
        _ensure_customer(db, account, case)
        reply = _visitor_details(account, case)
        db.commit()
    except IntegrityError:
        db.rollback()
        case = repository.intake(db, visitor_id, lock=False)
        if case is None:
            raise
        if case.advisor_id != principal.employee_id:
            raise BusinessError(409, "游客已被其他顾问认领") from None
        if case.crm_lead_id is None:
            raise
        return _visitor_details(db.get(VisitorAccount, visitor_id), case)
    except Exception:
        db.rollback()
        raise
    return reply


def _ensure_customer(db: Session, account: VisitorAccount, case: VisitorIntake) -> None:
    if case.crm_lead_id is not None:
        return
    claimed_at = _local_time(case.claimed_at)
    lead = CrmLead(
        customer_name=account.name or "未填写姓名", contact_info=account.contact,
        owner_employee_id=case.advisor_id, source_channel="website", status="contacting",
        create_time=claimed_at, update_time=now_naive(),
    )
    db.add(lead)
    db.flush()
    case.crm_lead_id = lead.id
    from .customer_service import attach_pending_portrait
    attach_pending_portrait(db, account.id, lead, account)
    from .status_events import LeadStatusEvent
    db.add(LeadStatusEvent(lead_id=lead.id, status="contacting", occurred_at=claimed_at))
    for call in repository.call_history(db, account.id):
        _sync_call(db, lead, call)


def backfill_claimed_customer(db: Session, visitor_id: int) -> bool:
    # Match claim's account → intake locking order so a retry cannot create another customer.
    account = repository.lock_visitor(db, visitor_id)
    case = repository.intake(db, visitor_id, lock=True) if account is not None else None
    if case is None or case.crm_lead_id is not None:
        return False
    _ensure_customer(db, account, case)
    return True


def add_call(db: Session, visitor_id: int, principal: EmployeePrincipal, payload: VisitorCallCreate) -> VisitorCallOut:
    require_permission(principal, "visitor-intake:write")
    try:
        case = _owned_case(db, visitor_id, principal.employee_id, lock=True)
        request_id = str(payload.request_id)
        call = repository.call_by_request(db, visitor_id, request_id)
        if call is None:
            now = utc_now()
            call = VisitorCall(
                visitor_id=visitor_id, advisor_id=principal.employee_id,
                request_id=request_id, notes=payload.notes, recorded_at=now,
            )
            case.last_contact_at = now
            db.add(call)
            if case.crm_lead_id is not None:
                _sync_call(db, _linked_lead(db, case), call)
            db.flush()
        elif call.notes != payload.notes:
            raise BusinessError(409, "该请求已用于保存另一条联系记录")
        reply = VisitorCallOut.model_validate(call)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return reply


def list_calls(db: Session, visitor_id: int, principal: EmployeePrincipal, before_id: int | None, limit: int):
    require_permission(principal, "visitor-intake:read")
    _owned_case(db, visitor_id, principal.employee_id)
    return [VisitorCallOut.model_validate(row) for row in repository.calls(db, visitor_id, before_id, limit)]


def list_materials(db: Session, visitor_id: int, principal: EmployeePrincipal, before_id: int | None, limit: int):
    require_permission(principal, "visitor-intake:read")
    _owned_case(db, visitor_id, principal.employee_id)
    return profiling.visitor_materials(db, visitor_id, before_id, limit)


def material_details(db: Session, visitor_id: int, source_id: int, principal: EmployeePrincipal) -> dict:
    require_permission(principal, "visitor-intake:read")
    _owned_case(db, visitor_id, principal.employee_id)
    return profiling.source_details(db, _visitor_source(db, visitor_id, source_id))


def preview_material(db: Session, visitor_id: int, source_id: int, principal: EmployeePrincipal) -> ReviewPreview:
    require_permission(principal, "visitor-intake:read")
    _owned_case(db, visitor_id, principal.employee_id)
    source = _visitor_source(db, visitor_id, source_id)
    text, filename = source.raw_content, source.file_name
    attachment = materials.visitor_attachment(db, visitor_id, source_id) if filename else None
    db.rollback()
    extracted = extract_text(filename, attachment) if filename and attachment else ""
    content = "\n".join(part.strip() for part in (text, extracted) if part and part.strip())
    if not content:
        raise BusinessError(422, "这份材料没有可读取的文字，请在初筛表中补录。")
    if len(content) > 48000:
        raise BusinessError(422, "研判文本超过工作流上限，请缩短或分批核对。")
    return review_text(content)


def material_attachment(db: Session, visitor_id: int, source_id: int, principal: EmployeePrincipal) -> tuple[str, bytes]:
    require_permission(principal, "visitor-intake:read")
    _owned_case(db, visitor_id, principal.employee_id)
    source = _visitor_source(db, visitor_id, source_id)
    content = materials.visitor_attachment(db, visitor_id, source_id)
    if content is None:
        raise BusinessError(404, "附件不存在")
    return source.file_name or f"material-{source_id}", content


def supplement(
    db: Session, visitor_id: int, principal: EmployeePrincipal, update: ScreeningInput, source_id: int | None,
) -> dict:
    require_permission(principal, "visitor-intake:write")
    try:
        case = _owned_case(db, visitor_id, principal.employee_id, lock=True)
        if case.last_contact_at is None:
            raise BusinessError(409, "请先保存联系记录")
        if source_id is None:
            source = _manual_source(db, case)
        else:
            source = _visitor_source(db, visitor_id, source_id, lock=True)
        result = profiling.analyze_source(db, source, principal.employee_id, update)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


def manual_screening(db: Session, visitor_id: int, principal: EmployeePrincipal) -> dict:
    require_permission(principal, "visitor-intake:read")
    case = _owned_case(db, visitor_id, principal.employee_id)
    if case.manual_source_id is None:
        raise BusinessError(404, "尚未保存补录资料")
    return profiling.source_details(db, db.get(CustomerSource, case.manual_source_id))


def _manual_source(db: Session, case: VisitorIntake) -> CustomerSource:
    if case.manual_source_id is not None:
        return db.get(CustomerSource, case.manual_source_id, with_for_update=True)
    # Pre-CRM data collected from the call remains separate from registration and visitor uploads.
    source = CustomerSource(source_type=SourceType.manual, parse_status=ParseStatus.success)
    db.add(source)
    db.flush()
    case.manual_source_id = source.id
    return source


def _visitor_source(db: Session, visitor_id: int, source_id: int, *, lock: bool = False) -> CustomerSource:
    source = materials.visitor_source(db, visitor_id, source_id, lock=lock)
    if source is None:
        raise BusinessError(404, "资料不存在")
    return source


def _owned_case(db: Session, visitor_id: int, advisor_id: int, *, lock: bool = False) -> VisitorIntake:
    case = repository.intake(db, visitor_id, lock=lock)
    if case is None or case.advisor_id != advisor_id:
        raise BusinessError(404, "游客联系记录不存在")
    return case


def _visitor_details(account: VisitorAccount, case: VisitorIntake) -> ClaimedVisitor:
    return ClaimedVisitor(
        visitor_id=account.id, registered_at=account.created_at, nickname=account.nickname, name=account.name,
        contact=account.contact, claimed_at=case.claimed_at, last_contact_at=case.last_contact_at,
        manual_source_id=case.manual_source_id, crm_lead_id=case.crm_lead_id,
    )


def create_lead(db: Session, visitor_id: int, principal: EmployeePrincipal, payload: VisitorLeadCreate) -> LeadOut:
    require_permission(principal, "visitor-intake:write")
    require_permission(principal, "crm:write")
    case = _owned_case(db, visitor_id, principal.employee_id)
    if payload.source_id != case.manual_source_id:
        _visitor_source(db, visitor_id, payload.source_id)
    if case.crm_lead_id is None:
        raise BusinessError(409, "该客户记录尚未生成，请重新打开跟进记录")
    return LeadOut.model_validate(_linked_lead(db, case))


def _linked_lead(db: Session, case: VisitorIntake) -> CrmLead:
    lead = repository.lock_lead(db, case.crm_lead_id, case.advisor_id)
    if lead is None:
        raise BusinessError(409, "当前客户记录不可用")
    return lead


def _local_time(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc).astimezone().replace(tzinfo=None)


def _sync_call(db: Session, lead: CrmLead, call: VisitorCall) -> None:
    recorded_at = _local_time(call.recorded_at)
    db.add(CrmFollowUp(
        lead_id=lead.id, employee_id=call.advisor_id, follow_type="phone",
        content=call.notes, create_time=recorded_at,
    ))
    if lead.last_contact_time is None or recorded_at > lead.last_contact_time:
        lead.last_contact_time = recorded_at
    lead.update_time = now_naive()
