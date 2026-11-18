from io import BytesIO
from uuid import uuid4

from PIL import Image, UnidentifiedImageError
from starlette.responses import Response
from urllib.parse import quote

from app.core.exceptions import BusinessError
from app.core.security.authorization import require_permission
from app.core.security.credentials import utc_now
from .models import LeaveAttachment, StudentAdminService

MAX_PROOF_BYTES = 5 * 1024 * 1024


def upload(db, student_id, filename, content):
    if not content or len(content) > MAX_PROOF_BYTES:
        raise BusinessError(422, "请上传不超过5MB的PDF、JPG或PNG证明")
    filename = (filename or "请假证明").replace("\\", "/").rsplit("/", 1)[-1][:255]
    if content.startswith(b"%PDF-"):
        content_type = "application/pdf"
    else:
        try:
            with Image.open(BytesIO(content)) as picture:
                content_type = {"JPEG": "image/jpeg", "PNG": "image/png"}.get(picture.format)
                picture.verify()
        except (ValueError, SyntaxError, UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise BusinessError(422, "附件须为有效的PDF、JPG或PNG") from exc
        if content_type is None:
            raise BusinessError(422, "附件须为PDF、JPG或PNG")
    row = LeaveAttachment(id=str(uuid4()), student_id=student_id, filename=filename,
                          content_type=content_type, content=content, created_at=utc_now())
    try:
        db.add(row)
        db.commit()
        return {"id": row.id, "filename": row.filename}
    except Exception:
        db.rollback()
        raise


def teacher_download(db, principal, leave_id):
    leave = teacher_leave(db, principal, leave_id)
    attachment = db.get(LeaveAttachment, leave.attachment_url) if leave.attachment_url else None
    if attachment is None or attachment.student_id != leave.student_id:
        raise BusinessError(404, "附件不存在")
    return Response(attachment.content, media_type=attachment.content_type, headers={
        "Content-Disposition": "attachment; filename*=UTF-8''" + quote(attachment.filename),
        "Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
    })


def teacher_leave(db, principal, leave_id):
    require_permission(principal, "leaves:read")
    leave = db.get(StudentAdminService, leave_id)
    if leave is None or leave.service_type != "leave" or leave.approver_id != principal.employee_id:
        raise BusinessError(404, "请假单不存在")
    return leave
