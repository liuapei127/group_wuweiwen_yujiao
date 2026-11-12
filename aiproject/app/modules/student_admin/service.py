from sqlalchemy.orm import Session
from app.modules.consultant.errors import ConflictError

from app.modules.student_admin.repository import StudentAdminRepository
from app.modules.student_admin.schemas import LeaveApprove


class StudentAdminServiceLayer:
    def __init__(self, db: Session):
        self.repo = StudentAdminRepository(db)

    def pending_leaves(self, approver_id: int | None):
        return self.repo.list_pending_leaves(approver_id)

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
        return self.repo.approve(row, payload.approver_id, payload.decision, payload.approval_comment)

    def _approve_and_sync(self, row, payload):
        from app.modules.todo.synchronization import synchronize_source
        db = self.repo.db
        try:
            row = self.repo.approve(row, payload.approver_id, payload.decision, payload.approval_comment)
            synchronize_source(db, "student_admin_service", row.id)
            db.commit()
            db.refresh(row)
            return row
        except Exception:
            db.rollback()
            raise
