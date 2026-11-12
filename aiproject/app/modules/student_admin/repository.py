from sqlalchemy import select, update
from app.modules.consultant.errors import ConflictError
from sqlalchemy.orm import Session

from app.modules.student_admin.models import StudentAdminService, SysUser
from app.shared.utils.time_util import now_naive


class StudentAdminRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_pending_leaves(self, approver_id: int | None, limit: int = 50) -> list[StudentAdminService]:
        stmt = select(StudentAdminService).where(
            StudentAdminService.service_type == "leave",
            StudentAdminService.status == "pending",
        )
        if not approver_id:
            raise PermissionError("必须提供可信审批人")
        stmt = stmt.where(StudentAdminService.approver_id == approver_id)
        stmt = stmt.order_by(StudentAdminService.id.asc()).limit(limit)
        return list(self.db.scalars(stmt).all())

    def get_leave(self, leave_id: int) -> StudentAdminService | None:
        row = self.db.get(StudentAdminService, leave_id)
        if row and row.service_type == "leave":
            return row
        return None

    def approve(self, row: StudentAdminService, approver_id: int, decision: str, comment: str | None) -> StudentAdminService:
        now = now_naive()
        result = self.db.execute(
            update(StudentAdminService).where(
                StudentAdminService.id == row.id,
                StudentAdminService.service_type == "leave",
                StudentAdminService.status == "pending",
                StudentAdminService.approver_id == approver_id,
            ).values(status=decision, approval_comment=comment, approval_time=now, update_time=now)
            .execution_options(synchronize_session=False)
        )
        if result.rowcount != 1:
            raise ConflictError("请假单已处理或审批范围已变化，请刷新后重试")
        self.db.refresh(row)
        return row

    def find_student_id_by_name(self, name: str) -> int | None:
        stmt = select(SysUser).where(SysUser.user_type == "student", SysUser.real_name == name, SysUser.status == "normal")
        users = list(self.db.scalars(stmt.limit(2)).all())
        if len(users) > 1:
            raise ConflictError("存在同名学生，请改用请假单 ID 审批")
        return users[0].id if users else None

    def find_pending_leave_by_student(self, student_id: int, approver_id: int) -> StudentAdminService | None:
        stmt = (
            select(StudentAdminService)
            .where(
                StudentAdminService.student_id == student_id,
                StudentAdminService.approver_id == approver_id,
                StudentAdminService.service_type == "leave",
                StudentAdminService.status == "pending",
            )
            .order_by(StudentAdminService.id.desc())
            .limit(2)
        )
        rows = list(self.db.scalars(stmt).all())
        if len(rows) > 1:
            raise ConflictError("存在多张待审批请假，请改用请假单 ID")
        return rows[0] if rows else None
