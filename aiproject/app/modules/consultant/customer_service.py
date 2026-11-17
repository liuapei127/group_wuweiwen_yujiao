import json
import re
from datetime import timedelta
from pathlib import PurePosixPath
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.security import EmployeePrincipal
from app.core.security.authorization import require_permission
from app.core.security.credentials import utc_now
from app.modules.auth.repository import AuthRepository
from app.modules.profile.customer_import import (
    EDUCATION_LABELS, PROJECT_LABELS, STAGE_LABELS, normalized_choice, normalized_name, normalized_phone, read_import,
)
from app.modules.profile import repository as material_repository
from app.modules.profile.dify_workflow import review_text
from app.modules.profile.models import CustomerProfile, CustomerSource, ParseStatus, SourceType, VisitorMaterial
from app.modules.profile.schemas import ScreeningInput, ScreeningStatus
from app.modules.profile.screening import screen_profile
from app.modules.profile.service import MAX_UPLOAD_BYTES, _RESULTS
from app.modules.visitor import repository as website_repo
from app.modules.visitor.models import MISSING_NAME, VisitorAccount
from app.shared.utils.time_util import now_naive

from . import customer_repository as repository
from .customer_models import CustomerIdentity, CustomerImportPreview
from .customer_schemas import ImportConfirm, SharedFields, VerifiedIdentity
from .models import CrmLead
from .repository import ConsultantRepository


_ACCOUNT_FIELDS = frozenset({"customer_name", "nickname", "contact_info"})
_SCREEN_FIELDS = frozenset({"age", "education_level", "education_stage", "intended_project", "intended_major"})


def list_managed_customers(
    db: Session, principal: EmployeePrincipal, *, keyword: str | None, status: str | None,
    page: int, page_size: int,
) -> dict:
    require_permission(principal, "crm:read")
    return repository.list_customers(
        db, principal.employee_id,
        missing_name=MISSING_NAME, keyword=keyword, status=status, page=page, page_size=page_size,
    )


def _admin(principal: EmployeePrincipal) -> None:
    if principal.role_code != "admin":
        raise BusinessError(403, "只有系统管理员可以核验客户身份")


def _read_website_link(db, visitor_id, *, lock=False):
    account = website_repo.lock_website_account(db, visitor_id) if lock else website_repo.profile_account(db, visitor_id)
    if account is None:
        raise BusinessError(401, "请重新登录官网")
    lead = repository.lead_for_visitor(db, visitor_id, lock=lock)
    return lead, account


def _staff_link(db: Session, lead_id: int, staff: EmployeePrincipal, *, write=False):
    require_permission(staff, "crm:write" if write else "crm:read")
    crm = ConsultantRepository(db)
    lead = crm.get_lead(lead_id)
    if lead is None or lead.owner_employee_id != staff.employee_id:
        raise BusinessError(404, "客户不存在")
    case = repository.case_for_lead(db, lead_id)
    account = None
    if case is not None and case.advisor_id == staff.employee_id:
        account = website_repo.lock_website_account(db, case.visitor_id) if write else website_repo.profile_account(db, case.visitor_id)
    if write:
        version = lead.profile_version
        lead = crm.lock_lead(lead_id)
        if lead is None or lead.owner_employee_id != staff.employee_id:
            raise BusinessError(404, "客户不存在")
        if account is None and lead.profile_version != version:
            raise BusinessError(409, "资料已更新，请刷新并核对最新资料")
    return lead, account


def _public_link(db, visitor, *, write=False):
    lead, account = _read_website_link(db, visitor.visitor_id, lock=write)
    if write and website_repo.session_visitor(db, visitor.digest, utc_now(), lock=True) != account.id:
        raise BusinessError(401, "请重新登录官网")
    if lead is None:
        raise BusinessError(409, "当前账号还没有客户记录")
    return lead, account


def _profile(lead: CrmLead, account: VisitorAccount | None):
    name = account.name if account else lead.customer_name
    return {
        "version": lead.profile_version,
        "customer_name": "" if name == MISSING_NAME else name,
        "nickname": account.nickname if account else None,
        "contact_info": account.contact if account else lead.contact_info,
        "age": lead.age, "education_level": lead.education_level, "education_stage": lead.education_stage,
        "intended_project": lead.intended_project, "intended_major": lead.intended_major,
    }


def _version(lead, expected: int):
    if lead.profile_version != expected:
        raise BusinessError(409, "资料已更新，请刷新并核对最新资料")


def _apply(lead, account, fields: dict):
    before = _profile(lead, account)
    for name, value in fields.items():
        if name in _ACCOUNT_FIELDS:
            if name == "customer_name":
                lead.customer_name = value or MISSING_NAME
                if account:
                    account.name = lead.customer_name
            elif name == "nickname":
                if account is None:
                    raise BusinessError(422, "关联官网账号后可编辑昵称")
                account.nickname = value or None
            else:
                lead.contact_info = value or ""
                if account:
                    account.contact = lead.contact_info
        elif name in _SCREEN_FIELDS:
            setattr(lead, name, value)
            if name == "intended_project":
                lead.intended_country = ("Germany" if value == "de_vocational" else "Singapore") if value else None
    if _profile(lead, account) != before:
        lead.profile_version += 1
        lead.update_time = now_naive()


def update_shared(db, lead, account, payload):
    _version(lead, payload.expected_version)
    _apply(lead, account, payload.model_dump(mode="json", exclude_unset=True, exclude={"expected_version"}))
    result = _profile(lead, account)
    db.commit()
    return result


def save_legacy_lead(db, lead_id, staff, payload):
    lead, account = _staff_link(db, lead_id, staff, write=True)
    fields = payload.model_dump(exclude_unset=True)
    previous_version = lead.profile_version
    if "contact_info" in fields:
        _apply(lead, account, {"contact_info": fields.pop("contact_info")})
    if "intended_country" in fields and lead.intended_project and fields["intended_country"] != lead.intended_country:
        raise BusinessError(422, "请在客户详情修改意向项目")
    if "intended_major" in fields:
        _apply(lead, account, {"intended_major": fields.pop("intended_major")})
    if lead.profile_version > previous_version:
        lead.profile_version = previous_version + 1
    for key, value in fields.items():
        setattr(lead, key, value)
    lead.update_time = now_naive()
    db.commit()
    db.refresh(lead)
    return lead


def website_profile_version(db, visitor_id):
    lead = repository.lead_for_visitor(db, visitor_id)
    return lead.profile_version if lead else None


def sync_existing_website_profile(db, account, payload):
    lead = repository.lead_for_visitor(db, account.id, lock=True)
    if lead is not None:
        if payload.expected_version is None:
            raise BusinessError(409, "客户资料已更新，请刷新后再保存")
        _version(lead, payload.expected_version)
        _apply(lead, account, {
            "customer_name": payload.name, "nickname": payload.nickname, "contact_info": payload.contact,
        })
    return lead is not None


def sync_website_booking_profile(db: Session, account: VisitorAccount, name: str | None, contact: str) -> bool:
    lead = repository.lead_for_visitor(db, account.id, lock=True)
    if lead is None:
        return False
    fields = {"contact_info": contact}
    if name is not None:
        fields["customer_name"] = name
    _apply(lead, account, fields)
    return True


def _screening_input(fields):
    return ScreeningInput(
        project=normalized_choice(fields["intended_project"], PROJECT_LABELS),
        age=fields["age"] if isinstance(fields["age"], int) and fields["age"] >= 0 else None,
        education=normalized_choice(fields["education_level"], EDUCATION_LABELS),
        education_stage=normalized_choice(fields["education_stage"], STAGE_LABELS),
    )


def readiness(fields):
    result = screen_profile(_screening_input(fields))
    return {"ready": not result.missing_fields, "missing_fields": result.missing_fields}


def staff_profile(db, lead_id, staff):
    lead, account = _staff_link(db, lead_id, staff)
    fields = _profile(lead, account)
    last = repository.newest_screening(db, lead.id)
    return {
        **fields, "website_linked": account is not None,
        "visitor_id": account.id if account is not None and "visitor-intake:read" in staff.permissions else None,
        "readiness": readiness(fields),
        "screening": _screening_response(last, lead.profile_version) if last else None,
    }


def visitor_profile(db, visitor):
    lead, account = _public_link(db, visitor)
    return {**_profile(lead, account), "imports": [dict(row) for row in repository.visitor_imports(db, lead.id, account.id)]}


def save_staff_profile(db, lead_id, staff, payload):
    return update_shared(db, *_staff_link(db, lead_id, staff, write=True), payload)


def save_visitor_profile(db, visitor, payload):
    return update_shared(db, *_public_link(db, visitor, write=True), payload)


def draft_readiness(db, lead_id, staff, draft: SharedFields):
    lead, account = _staff_link(db, lead_id, staff)
    fields = _profile(lead, account) | draft.model_dump(mode="json", exclude_unset=True)
    return readiness(fields)


def save_identity(db: Session, lead_id: int, payload: VerifiedIdentity, staff: EmployeePrincipal):
    _admin(staff)
    require_permission(staff, "website-accounts:manage")
    try:
        lead = ConsultantRepository(db).lock_lead(lead_id)
        if lead is None:
            raise BusinessError(404, "客户不存在")
        identity = db.get(CustomerIdentity, lead.id)
        existing = repository.identity_by_phone(db, payload.mobile)
        if existing and existing.lead_id != lead.id:
            raise BusinessError(409, "该核验手机号已属于其他客户")
        if identity is None:
            identity = CustomerIdentity(lead_id=lead.id)
            db.add(identity)
        identity.verified_name = normalized_name(payload.name)
        identity.verified_mobile = payload.mobile
        identity.verified_by = staff.employee_id
        identity.verified_at = utc_now()
        lead.profile_version += 1
        AuthRepository(db).audit(staff.employee_id, "customer_identity_verified", lead.id)
        db.commit()
        return {"verified": True}
    except IntegrityError:
        db.rollback()
        raise BusinessError(409, "该核验手机号已属于其他客户") from None
    except Exception:
        db.rollback()
        raise


def _preview(db, lead, account, actor, file_name, content, extracted):
    text, name, mobile, proposed = extracted
    current = _profile(lead, account)
    identity = db.get(CustomerIdentity, lead.id)
    phone_owner = repository.identity_by_phone(db, mobile)
    if phone_owner is not None and phone_owner.lead_id != lead.id:
        raise BusinessError(422, "文件中的手机号已核验为其他客户，请核对资料归属")
    if identity is not None:
        matches = identity.verified_name == name and identity.verified_mobile == mobile
    else:
        phones = {normalized_phone(current["contact_info"] or "")}
        if account is not None:
            phones.add(normalized_phone(account.username))
        matches = normalized_name(current["customer_name"]) == name and mobile in phones
    if not matches:
        raise BusinessError(422, "无法确认资料归属，请核对文件中的姓名和本人手机号是否与当前客户一致")
    proposed = {k: v for k, v in proposed.items() if current[k] != v and (k != "nickname" or account)}
    if not proposed:
        raise BusinessError(422, "文件中没有可补充的资料字段")
    now = utc_now()
    repository.clean_expired_previews(db, now)
    preview = CustomerImportPreview(
        id=str(uuid4()), lead_id=lead.id, actor_kind=actor[0], actor_id=actor[1],
        profile_version=lead.profile_version, file_name=file_name, file_content=content, raw_content=text,
        proposed=proposed, expires_at=now + timedelta(minutes=30),
    )
    db.add(preview)
    result = {
        "preview_id": preview.id, "version": lead.profile_version, "file_name": file_name,
        "matches": ["姓名", "本人手机号"],
        "fields": [{"field": key, "current": current[key], "proposed": v} for key, v in proposed.items()],
    }
    db.commit()
    return result


def _extract_upload(filename, content):
    name = PurePosixPath((filename or "").replace(chr(92), "/")).name
    if not name or len(name) > 255 or not content or len(content) > MAX_UPLOAD_BYTES:
        raise BusinessError(422, "请选择有效文件，大小不能超过 10 MB")
    return name, read_import(name, content)


def preview_staff(db, lead_id, staff, filename, content):
    _staff_link(db, lead_id, staff, write=True)
    db.rollback()
    file_name, extracted = _extract_upload(filename, content)
    return _preview(db, *_staff_link(db, lead_id, staff, write=True), ("employee", staff.employee_id), file_name, content, extracted)


def _material_for_import(db, lead, account, source_id):
    source = material_repository.visitor_source(db, account.id, source_id, lock=True) if account else None
    if source is None or source.lead_id not in (None, lead.id):
        raise BusinessError(404, "资料不存在")
    content = material_repository.visitor_attachment(db, account.id, source_id)
    if content is None:
        if source.file_name:
            raise BusinessError(404, "附件不存在")
        content = (source.raw_content or "").encode("utf-8")
    return source, source.file_name or "文字资料.txt", content


def preview_staff_material(db, lead_id, source_id, staff):
    require_permission(staff, "visitor-intake:read")
    lead, account = _staff_link(db, lead_id, staff, write=True)
    _, file_name, content = _material_for_import(db, lead, account, source_id)
    db.rollback()
    _, extracted = _extract_upload(file_name, content)
    lead, account = _staff_link(db, lead_id, staff, write=True)
    _, latest_name, latest_content = _material_for_import(db, lead, account, source_id)
    if (latest_name, latest_content) != (file_name, content):
        raise BusinessError(409, "材料已更新，请重新识别")
    return _preview(db, lead, account, ("employee", staff.employee_id), file_name, content, extracted)


def preview_visitor(db, visitor, filename, content):
    _public_link(db, visitor)
    db.rollback()
    file_name, extracted = _extract_upload(filename, content)
    return _preview(db, *_public_link(db, visitor, write=True), ("visitor", visitor.visitor_id), file_name, content, extracted)


def _confirm(db, lead, account, actor, payload: ImportConfirm):
    _version(lead, payload.expected_version)
    preview = repository.preview_for_update(db, str(payload.preview_id))
    if (preview is None or preview.lead_id != lead.id or (preview.actor_kind, preview.actor_id) != actor
            or preview.expires_at <= utc_now()):
        raise BusinessError(404, "上传预览已失效，请重新上传")
    _version(lead, preview.profile_version)
    selected = set(payload.fields)
    if not selected <= preview.proposed.keys():
        raise BusinessError(422, "请选择预览中已识别的字段")
    source = None
    if payload.source_id is not None:
        source, file_name, content = _material_for_import(db, lead, account, payload.source_id)
        if (file_name, content) != (preview.file_name, preview.file_content):
            raise BusinessError(409, "材料与识别预览不一致，请重新识别")
    delta = {key: value for key, value in preview.proposed.items() if key in selected}
    _apply(lead, account, delta)
    source_types = {
        ".pdf": SourceType.pdf_resume, ".xlsx": SourceType.excel, ".xls": SourceType.excel,
        ".csv": SourceType.import_,
    }
    if source is None:
        source = CustomerSource(
            source_type=source_types.get(PurePosixPath(preview.file_name).suffix.lower(), SourceType.text),
            raw_content=preview.raw_content, file_name=preview.file_name,
            file_content=preview.file_content if actor[0] == "employee" else None,
            operator_id=actor[1] if actor[0] == "employee" else None,
        )
        db.add(source)
        db.flush()
        if actor[0] == "visitor":
            db.add(VisitorMaterial(source_id=source.id, visitor_id=actor[1], file_content=preview.file_content))
    source.lead_id = lead.id
    source.parse_status = ParseStatus.success
    source.parse_result = {"customer_id": lead.id, "confirmed_fields": delta}
    db.delete(preview)
    result = _profile(lead, account)
    db.commit()
    return result


def confirm_staff(db, lead_id, staff, payload):
    if payload.source_id is not None:
        require_permission(staff, "visitor-intake:read")
    return _confirm(db, *_staff_link(db, lead_id, staff, write=True), ("employee", staff.employee_id), payload)


def confirm_visitor(db, visitor, payload):
    return _confirm(db, *_public_link(db, visitor, write=True), ("visitor", visitor.visitor_id), payload)


def _advice_section(text, label, following):
    match = re.search(label + r"[：:]\s*(.+?)(?=" + following + r"[：:]|\Z)", text, re.S)
    return match[1].strip() if match else ""


def _generate_advice(fields, official):
    encoded = json.dumps({
        "name": fields["customer_name"],
        "age": fields["age"],
        "education": EDUCATION_LABELS.get(fields["education_level"], fields["education_level"]),
        "education_stage": STAGE_LABELS.get(fields["education_stage"], fields["education_stage"]),
        "target_project": PROJECT_LABELS.get(fields["intended_project"], fields["intended_project"]),
        "core_demand": fields["intended_major"],
        "profile_summary": "本地初筛依据：" + "；".join(official.findings),
    }, ensure_ascii=False)
    reply = review_text(encoded)
    text = reply.advisor_advice or reply.match_reason
    talk = _advice_section(text, "沟通时可以这样说", "还缺这些资料|下一步先问")
    next_step = _advice_section(text, "下一步先问", "沟通时可以这样说|还缺这些资料")
    if not talk or not next_step:
        raise BusinessError(502, "AI 未返回完整建议和话术，可以重新研判")
    return {"state": "ready", "recommendation": next_step.strip(" *"), "talk_track": talk.strip(" *")}


def _screening_response(row, current_version):
    data = row.background_info or {}
    return {
        "id": row.id, "version": row.profile_version, "stale": row.profile_version != current_version,
        "result": data.get("screening"), "ai": data.get("ai"),
    }


def run_screening(db, lead_id, staff, expected_version):
    lead, account = _staff_link(db, lead_id, staff, write=True)
    _version(lead, expected_version)
    fields = _profile(lead, account)
    checked = _screening_input(fields)
    official = screen_profile(checked)
    if official.status == ScreeningStatus.NEEDS_INFORMATION:
        return {"ready": False, "missing_fields": official.missing_fields}
    data = {
        "input": checked.model_dump(mode="json"),
        "screening": official.model_dump(mode="json"),
        "ai": {"state": "pending"},
    }
    row = CustomerProfile(
        lead_id=lead.id, profile_version=lead.profile_version, background_info=data,
        match_result=_RESULTS[official.status], match_reason="；".join(official.findings),
        evaluator_id=staff.employee_id,
    )
    db.add(row)
    db.flush()
    screening_id = row.id
    lead.customer_profile_id = screening_id
    db.commit()
    try:
        ai = _generate_advice(fields, official)
    except BusinessError as exc:
        ai = {"state": "unavailable", "message": str(exc)}
    row = db.get(CustomerProfile, screening_id)
    row.background_info = {**data, "ai": ai}
    db.commit()
    latest_lead = ConsultantRepository(db).get_lead(lead_id)
    return {"ready": True, "screening": _screening_response(row, latest_lead.profile_version)}
