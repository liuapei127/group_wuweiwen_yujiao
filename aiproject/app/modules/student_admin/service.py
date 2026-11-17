from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.modules.student.notifications import save_student_result
from app.modules.student_admin.models import StudentAdminService
from app.modules.student_admin.models import LeaveAttachment
from app.modules.consultant.errors import ConflictError

from app.modules.student_admin.repository import StudentAdminRepository
from app.modules.student_admin.schemas import LeaveApprove, LeaveOut, StudentLeaveCreate


_BEIJING = timezone(timedelta(hours=8))


class StudentAdminServiceLayer:
    def __init__(self, db: Session):
        self.repo = StudentAdminRepository(db)

    def submit_student_leave(
        self, student_id: int, payload: StudentLeaveCreate, *, commit: bool = True
    ) -> LeaveOut:
        """提交人 ID 由调用方的可信学生身份提供。"""
        from app.modules.todo.synchronization import synchronize_source

        db = self.repo.db
        try:
            if not self.repo.lock_student(student_id):
                raise BusinessError(403, "学生账号不可用")
            now = datetime.now(_BEIJING).replace(tzinfo=None, microsecond=0)
            day_start = now.replace(hour=0, minute=0, second=0)
            if self.repo.has_identical_submission(
                student_id, payload.start_time, payload.end_time, day_start, day_start + timedelta(days=1)
            ):
                raise BusinessError(409, "今天已提交过相同时间段的请假")
            approver_id = self.repo.class_teacher(student_id)
            if approver_id is None:
                raise BusinessError(409, "尚未分配有效班主任")
            attachment_id = str(payload.attachment_id) if payload.attachment_id else None
            if attachment_id:
                attachment = db.get(LeaveAttachment, attachment_id, with_for_update=True)
                if attachment is None or attachment.student_id != student_id:
                    raise BusinessError(422, "附件不存在或不属于该学生")
            row = StudentAdminService(
                student_id=student_id, service_type="leave", leave_type=payload.leave_type,
                start_time=payload.start_time, end_time=payload.end_time, reason=payload.reason,
                status="pending", approver_id=approver_id, create_time=now, update_time=now,
                attachment_url=attachment_id,
            )
            self.repo.add_leave(row)
            synchronize_source(db, "student_admin_service", row.id)
            result = LeaveOut.model_validate(row)
            if commit:
                db.commit()
        except Exception:
            db.rollback()
            raise
        return result

    def student_leaves(self, student_id: int, before_id: int | None, limit: int) -> list[LeaveOut]:
        return [LeaveOut.model_validate(row) for row in self.repo.list_student_leaves(student_id, before_id, limit)]

    def student_leave(self, student_id: int, leave_id: int) -> LeaveOut:
        row = self.repo.get_leave(leave_id)
        if row is None or row.student_id != student_id:
            raise BusinessError(404, "请假单不存在")
        return LeaveOut.model_validate(row)

    def pending_leaves(self, approver_id: int | None):
        return self.repo.list_pending_leaves(approver_id)

    def pending_leave_candidates(self, approver_id: int, student_name: str):
        return self.repo.pending_leave_candidates(approver_id, student_name)

    def approve_leave(self, leave_id: int, payload: LeaveApprove):
        row = self.repo.get_leave(leave_id)
        if not row:
            raise ValueError("请假单不存在")
        if row.approver_id != payload.approver_id:
            raise PermissionError("仅指定审批人可审批；未分配单据暂不可处理")
        if row.status != "pending":
            raise ConflictError("仅待审批状态可处理")
        return self._approve_and_sync(row, payload)

    def approve_leave_by_student_name(self, student_name: str, payload: LeaveApprove):
        student_id = self.repo.find_student_id_by_name(student_name)
        if not student_id:
            raise ValueError(f"未找到学生：{student_name}")
        row = self.repo.find_pending_leave_by_student(student_id, payload.approver_id)
        if not row:
            raise ValueError("该学生没有待审批请假")
        return self._approve_and_sync(row, payload)

    def _approve_and_sync(self, row, payload):
        from app.modules.todo.synchronization import synchronize_source
        db = self.repo.db
        try:
            row = self.repo.approve(row, payload.approver_id, payload.decision, payload.approval_comment)
            synchronize_source(db, "student_admin_service", row.id)
            decision_text = "已通过" if row.status == "approved" else "已拒绝"
            save_student_result(db, row.student_id, "student_admin_service", row.id, row.status,
                                "请假审批结果", "你的请假申请" + decision_text + "。")
            db.commit()
            db.refresh(row)
            return row
        except Exception:
            db.rollback()
            raise
