import json
import re
from pathlib import PurePosixPath

from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError

from . import repository
from .extract import extract_text
from .dify_workflow import ReviewPreview, review_text
from .models import CustomerProfile, CustomerSource, MatchResult, ParseStatus, SourceType, VisitorMaterial
from .schemas import ScreeningInput, ScreeningStatus, VisitorMaterialProgress
from .screening import screen_profile

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
_MAX_TEXT_BYTES = 60_000
_RESULTS = {
    ScreeningStatus.NEEDS_INFORMATION: MatchResult.partial,
    ScreeningStatus.NEEDS_REVIEW: MatchResult.partial,
    ScreeningStatus.POTENTIAL_MATCH: MatchResult.matched,
    ScreeningStatus.NOT_MATCHED: MatchResult.not_matched,
}


def upload_source(
    db: Session,
    employee_id: int,
    source_type: SourceType,
    raw_content: str | None,
    filename: str | None,
    content: bytes | None,
) -> dict:
    if content is not None and (not content or len(content) > MAX_UPLOAD_BYTES):
        raise BusinessError(422, "文件为空或超过 10 MB")
    if not raw_content and content is None:
        raise BusinessError(422, "请提供资料文字或上传文件")
    filename = PurePosixPath(filename.replace("\\", "/")).name if filename else None
    if filename and len(filename) > 255:
        raise BusinessError(422, "文件名超过 255 个字符")
    extracted = extract_text(filename or "", content) if content is not None else ""
    body = "\n".join(part for part in (raw_content, extracted) if part and part.strip())
    if len(body.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise BusinessError(422, "资料正文过长")
    if not body:
        raise BusinessError(422, "文件没有可读取的正文，请补充文字")
    try:
        parsed = json.loads(extracted or body)
    except json.JSONDecodeError:
        parsed = None
    if isinstance(parsed, list) and sum(isinstance(item, dict) for item in parsed) > 1:
        raise BusinessError(422, "一份资料只能包含一位客户")
    source = CustomerSource(
        source_type=source_type, raw_content=body, file_name=filename,
        operator_id=employee_id, parse_status=ParseStatus.success,
        parse_result={"fields": parsed} if isinstance(parsed, dict) else None,
    )
    db.add(source)
    db.flush()
    response = {"source_id": source.id, "parse_status": source.parse_status}
    db.commit()
    return response


def get_judgment(db: Session, source_id: int, employee_id: int) -> dict:
    source = _require_owned(db, source_id, employee_id)
    return source_details(db, source)


def source_details(db: Session, source: CustomerSource) -> dict:
    result = repository.latest_profile(db, source.id)
    background = (result.background_info or {}) if result else {}
    return {
        "source_id": source.id,
        "parse_status": source.parse_status,
        "file_name": source.file_name,
        "raw_content": source.raw_content,
        "extracted_fields": (source.parse_result or {}).get("fields"),
        "screening_input": background.get("input"),
        "screening": background.get("screening"),
    }


def request_analysis(db: Session, source_id: int, employee_id: int, update: ScreeningInput) -> dict:
    source = _require_owned(db, source_id, employee_id, for_update=True)
    result = analyze_source(db, source, employee_id, update)
    db.commit()
    return result


def analyze_source(db: Session, source: CustomerSource, employee_id: int, update: ScreeningInput) -> dict:
    """由调用方核验资料归属、锁定资料并提交事务。"""
    previous = repository.latest_profile(db, source.id, lock=True)
    previous_fields = (previous.background_info or {}).get("input", {}) if previous else {}
    fields = ScreeningInput.model_validate({**previous_fields, **update.model_dump(exclude_unset=True)})
    result = screen_profile(fields)
    background = {"input": fields.model_dump(mode="json"), "screening": result.model_dump(mode="json")}
    if previous is None or previous.background_info != background:
        db.add(CustomerProfile(
            source_id=source.id, background_info=background, match_result=_RESULTS[result.status],
            match_reason="；".join(result.findings) or None, evaluator_id=employee_id,
        ))
    return {"source_id": source.id, "screening": result}


def _require_owned(
    db: Session, source_id: int, employee_id: int, *, for_update: bool = False
) -> CustomerSource:
    source = repository.get_owned_source(db, source_id, employee_id, for_update=for_update)
    if source is None:
        raise BusinessError(404, "客户资料不存在")
    return source


_VISITOR_FILE_TYPES = {
    ".txt": SourceType.text,
    ".csv": SourceType.import_,
    ".pdf": SourceType.pdf_resume,
    ".xls": SourceType.excel,
    ".xlsx": SourceType.excel,
}


def submit_visitor_material(
    db: Session, visitor_id: int, raw_content: str | None, filename: str | None, content: bytes | None,
) -> VisitorMaterialProgress:
    text = (raw_content or "").strip()
    if not text and content is None:
        raise BusinessError(422, "请提交已有的文字或文件")
    if len(text.encode("utf-8")) > _MAX_TEXT_BYTES:
        raise BusinessError(422, "资料正文过长")
    source_type = SourceType.text
    file_name = None
    if content is not None:
        if not content or len(content) > MAX_UPLOAD_BYTES:
            raise BusinessError(422, "文件为空或超过 10 MB")
        file_name = PurePosixPath((filename or "").replace(chr(92), "/")).name
        if len(file_name) > 255:
            raise BusinessError(422, "文件名超过 255 个字符")
        extension = PurePosixPath(file_name).suffix.lower()
        if extension not in _VISITOR_FILE_TYPES:
            raise BusinessError(422, "支持 TXT、CSV、PDF、XLS 和 XLSX 文件")
        source_type = _VISITOR_FILE_TYPES[extension]

    try:
        source = CustomerSource(
            source_type=source_type, raw_content=text or None, file_name=file_name,
            parse_status=ParseStatus.pending,
        )
        db.add(source)
        db.flush()
        db.add(VisitorMaterial(source_id=source.id, visitor_id=visitor_id, file_content=content))
        _apply_verified_submission(db, visitor_id, text, file_name, content)
        result = _visitor_progress(source, None)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


def _apply_verified_submission(db, visitor_id, text, file_name, content):
    from app.modules.consultant.customer_service import record_visitor_portrait
    from app.modules.visitor.repository import lock_website_account

    from .customer_import import normalized_name, normalized_phone, read_import
    from .portrait import person_updates, stated_name

    document = content if content is not None else text.encode("utf-8")
    try:
        _, name, mobile, fields = read_import(file_name or "资料.txt", document)
    except BusinessError:
        name = mobile = ""
        fields = {}
    account = lock_website_account(db, visitor_id)
    if account is None:
        return
    if account.has_name and normalized_name(account.name) == name and normalized_phone(account.username) == mobile:
        record_visitor_portrait(db, visitor_id, "", source="visitor_material", extracted=fields)
        return
    # A signed-in visitor can also submit a first-person note. A file or a note
    # with explicit identity fields stays in the original material review flow.
    if content is None and not re.search(r"姓名\s*[:：]|手机号|(?<!\d)1[3-9]\d{9}(?!\d)|[{}\[\]]", text):
        note_name = stated_name(text)
        if not note_name or (account.has_name and normalized_name(account.name) == normalized_name(note_name)):
            record_visitor_portrait(db, visitor_id, "", source="visitor_material", extracted=person_updates(text))


def visitor_materials(
    db: Session, visitor_id: int, before_id: int | None, limit: int,
) -> list[VisitorMaterialProgress]:
    sources = repository.visitor_sources(db, visitor_id, limit, before_id=before_id)
    profiles = repository.latest_profiles(db, [source.id for source in sources])
    return [_visitor_progress(source, profiles.get(source.id)) for source in sources]


def visitor_material(db: Session, visitor_id: int, source_id: int) -> VisitorMaterialProgress:
    sources = repository.visitor_sources(db, visitor_id, 1, source_id=source_id)
    if not sources:
        raise BusinessError(404, "资料不存在")
    return _visitor_progress(sources[0], repository.latest_profile(db, source_id))


def _visitor_progress(source: CustomerSource, result: CustomerProfile | None) -> VisitorMaterialProgress:
    status = "imported" if source.parse_status == ParseStatus.success and "confirmed_fields" in (source.parse_result or {}) else "received"
    if result is not None:
        screening = (result.background_info or {}).get("screening") or {}
        status = "needs_information" if screening.get("status") == ScreeningStatus.NEEDS_INFORMATION else "reviewed"
    return VisitorMaterialProgress(
        source_id=source.id, file_name=source.file_name, submitted_at=source.create_time, status=status,
    )


def list_advisor_sources(db: Session, employee_id: int, before_id: int | None, limit: int) -> list[dict]:
    rows = repository.advisor_sources(db, employee_id, before_id, limit)
    profiles = repository.latest_profiles(db, [row.id for row in rows])
    return [
        {
            "source_id": row.id, "file_name": row.file_name, "submitted_at": row.create_time,
            "screening": ((profiles[row.id].background_info or {}).get("screening")
                          if row.id in profiles else None),
        }
        for row in rows
    ]


def preview_advisor_source(db: Session, source_id: int, employee_id: int) -> ReviewPreview:
    source = _require_owned(db, source_id, employee_id)
    content = source.raw_content
    db.rollback()
    if not content or len(content) > 48000:
        raise BusinessError(422, "资料为空或超过研判长度限制")
    return review_text(content)
