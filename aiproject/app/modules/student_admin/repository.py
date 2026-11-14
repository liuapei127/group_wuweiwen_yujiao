from datetime import datetime

from sqlalchemy import select, update
from app.modules.auth.repository import student_info
from app.modules.consultant.errors import ConflictError
from sqlalchemy.orm import Session

from app.modules.student_admin.models import StudentAdminService, SysUser
from app.shared.utils.time_util import now_naive


class StudentAdminRepository:
    def __init__(self, db: Session):
        self.db = db

    def list_student_leaves(self, student_id: int, before_id: int | None, limit: int) -> list[StudentAdminService]:
        stmt = select(StudentAdminService).where(
            StudentAdminService.student_id == student_id, StudentAdminService.service_type == "leave"
        )
        if before_id is not None:
            stmt = stmt.where(StudentAdminService.id < before_id)
        return list(self.db.scalars(stmt.order_by(StudentAdminService.id.desc()).limit(limit)))

    def lock_student(self, student_id: int) -> bool:
        stmt = select(SysUser.id).where(
            SysUser.id == student_id, SysUser.user_type == "student", SysUser.status == "normal"
        ).with_for_update()
        return self.db.scalar(stmt) is not None

    def class_teacher(self, student_id: int) -> int | None:
        stmt = (
            select(SysUser.id)
            .join(student_info, student_info.c.class_teacher_id == SysUser.id)
            .where(student_info.c.user_id == student_id, SysUser.user_type == "employee", SysUser.status == "normal")
            .limit(2)
            .with_for_update()
        )
        ids = self.db.scalars(stmt).all()
        return ids[0] if len(ids) == 1 else None

    def has_identical_submission(
        self, student_id: int, start: datetime, end: datetime, day_start: datetime, day_end: datetime
    ) -> bool:
        stmt = select(StudentAdminService.id).where(
            StudentAdminService.student_id == student_id,
            StudentAdminService.service_type == "leave",
            StudentAdminService.start_time == start,
            StudentAdminService.end_time == end,
            StudentAdminService.create_time >= day_start,
            StudentAdminService.create_time < day_end,
        ).limit(1).with_for_update()
        return self.db.scalar(stmt) is not None

    def add_leave(self, leave: StudentAdminService) -> None:
        self.db.add(leave)
        self.db.flush()

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
