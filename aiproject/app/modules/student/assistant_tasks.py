"""Durable drafts. Only an owned, versioned confirmation may execute a business write."""
from datetime import timedelta
from secrets import token_hex
from pydantic import ValidationError
from app.core.exceptions import BusinessError
from app.shared.utils.time_util import now_naive
from app.modules.student_admin.schemas import StudentLeaveCreate
from app.modules.student_admin.service import StudentAdminServiceLayer
from app.modules.feedback.schemas import StudentComplaintCreate
from app.modules.feedback import service as feedback
from .models import StudentAssistantTask
from . import assistant_workspace_repository as repo

ACTIVE = ("collecting", "awaiting_confirmation")
LABELS = {"leave_type": "假别", "start_time": "开始时间（北京时间）", "end_time": "结束时间（北京时间）",
          "reason": "事由", "ticket_type": "反馈方式", "category": "所属业务", "content": "具体内容"}
VALUES = {"sick": "病假", "personal": "事假", "emergency": "紧急事由", "complaint": "正式投诉",
          "suggestion": "建议", "learning": "学习事务，交班主任处理", "company": "交主管处理（不展示给班主任）"}


def view(row):
    if row is None:
        return None
    keys = ("leave_type", "start_time", "end_time", "reason") if row.kind == "leave" else ("ticket_type", "category", "content")
    status = "expired" if row.status in ACTIVE and row.expires_at <= now_naive() else row.status
    from .assistant_guidance import for_task
    return {"guide":for_task(row.kind,row.payload,status), "form_values":{key:row.payload.get(key) for key in keys}, "id": row.id, "kind": row.kind, "status": status, "version": row.version, "ordinal": row.ordinal, "updated_at": row.update_time.isoformat(),
            "conversation_id": row.conversation_id, "expires_at": row.expires_at.isoformat(),
            "attachment": {"id": row.payload["attachment_id"], "filename": row.payload.get("attachment_filename", "请假证明")} if row.kind == "leave" and row.payload.get("attachment_id") else None,
            "fields": [{"label": LABELS[k], "value": VALUES.get(str(row.payload.get(k)), str(row.payload.get(k) or "待补充"))} for k in keys],
            "missing": [LABELS[k] for k in keys if not row.payload.get(k)], "result": row.result}


def validate(kind, payload):
    cls = StudentLeaveCreate if kind == "leave" else StudentComplaintCreate
    return cls.model_validate({k: v for k, v in payload.items() if k in cls.model_fields})


def save_draft(db, sid, cid, kind, payload, expected):
    if kind == "feedback" and feedback.personnel_complaint(payload.get("content", "")):
        payload = {**payload, "category": "company"}
    if repo.conversation(db, sid, cid, lock=True) is None:
        raise BusinessError(404, "对话不存在")
    current = repo.latest_task(db, sid, cid, active=True, lock=True)
    actual = (current.id, current.version) if current else None
    if actual != expected:
        db.rollback()
        raise BusinessError(409, "这份草稿已在另一处更新，请重新打开对话")
    now = now_naive()
    if current and (current.kind != kind or current.expires_at <= now):
        current.status = "expired" if current.expires_at <= now else "cancelled"
        current.version += 1
        current.update_time = now
        db.flush()
        current = None
    if current is None:
        current = StudentAssistantTask(id=token_hex(16), student_id=sid, conversation_id=cid,
            kind=kind, ordinal=repo.next_ordinal(db, sid, cid), status="collecting", payload={},
            result=None, version=0, create_time=now, update_time=now, expires_at=now + timedelta(hours=24))
        db.add(current)
    current.payload = payload
    current.version += 1
    current.update_time = now
    current.expires_at = now + timedelta(hours=24)
    try:
        validate(kind, payload)
        current.status = "awaiting_confirmation"
    except ValidationError:
        current.status = "collecting"
    db.commit()
    return view(current)


def decide(db, sid, task_id, expected_version, *, cancel=False):
    # Same lock order as draft edits: conversation -> task -> business student row.
    found = repo.task(db, sid, task_id)
    if found is None:
        raise BusinessError(404, "办理草稿不存在")
    cid = found.conversation_id
    repo.conversation(db, sid, cid, lock=True)
    db.expire_all()
    row = repo.task(db, sid, task_id, lock=True)
    if row is None:
        raise BusinessError(404, "办理草稿不存在")
    if row.status == "submitted" and not cancel:
        result = view(row)
        db.commit()
        return result  # response lost/repeated click: replay durable result
    if row.status == "cancelled" and cancel:
        result = view(row)
        db.commit()
        return result
    if row.version != expected_version:
        raise BusinessError(409, "草稿已更新，请核对最新内容后再确认")
    if row.status not in ACTIVE:
        raise BusinessError(409, "这份草稿已结束，请重新发起")
    now = now_naive()
    if row.expires_at <= now:
        row.status = "expired"
        row.version += 1
        db.commit()
        raise BusinessError(409, "草稿已过期，请重新确认时间和内容")
    try:
        if cancel:
            row.status = "cancelled"
        else:
            if row.status != "awaiting_confirmation":
                raise BusinessError(422, "资料尚未完整，请先补充")
            payload = validate(row.kind, row.payload)
            if row.kind == "leave":
                result = StudentAdminServiceLayer(db).submit_student_leave(sid, payload, commit=False)
            else:
                result = feedback.submit_student_complaint(db, sid, payload, commit=False)
            row.result = result.model_dump(mode="json")
            row.status = "submitted"
        row.version += 1
        row.update_time = now
        db.commit()  # Business row, staff todo and receipt succeed/fail together.
        return view(row)
    except Exception:
        db.rollback()
        raise


def change_attachment(db, sid, task_id, expected_version, attachment_id):
    """Attach only an owned uploaded proof to an active owned draft; invalidate old confirmation."""
    from app.modules.student_admin.models import LeaveAttachment
    found = repo.task(db, sid, task_id)
    if found is None:
        raise BusinessError(404, "办理草稿不存在")
    try:
        repo.conversation(db, sid, found.conversation_id, lock=True)
        db.expire_all()
        row = repo.task(db, sid, task_id, lock=True)
        if row is None or row.kind != "leave":
            raise BusinessError(404, "请假草稿不存在")
        if row.version != expected_version:
            raise BusinessError(409, "草稿已更新，请刷新后再添加附件")
        if row.status not in ACTIVE or row.expires_at <= now_naive():
            raise BusinessError(409, "草稿已结束或过期")
        payload = dict(row.payload)
        if attachment_id:
            attachment = db.get(LeaveAttachment, attachment_id, with_for_update=True)
            if attachment is None or attachment.student_id != sid:
                raise BusinessError(422, "附件不存在或不属于本人")
            payload.update(attachment_id=attachment.id, attachment_filename=attachment.filename)
        else:
            payload.pop("attachment_id", None)
            payload.pop("attachment_filename", None)
        row.payload = payload
        row.version += 1
        row.update_time = now_naive()
        row.expires_at = row.update_time + timedelta(hours=24)
        result = view(row)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise
