from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.security import EmployeePrincipal
from app.core.security.authorization import require_permission, require_student_scope
from app.modules.auth.repository import AuthRepository
from app.modules.todo.synchronization import synchronize_source
from app.modules.visitor.repository import lock_eligible_teacher, teacher_options
from app.modules.student_admin.repository import StudentAdminRepository
from app.core.security.credentials import utc_now

from . import repository
from .models import ClassEnrollment, ClassPlacementHistory, ProjectClass, TeachingProject
from .schemas import ClassPlacement, ClassWrite, ProjectWrite, StudentPlacementWrite


@dataclass(frozen=True)
class ClassAssignment:
    class_id: int
    teacher_id: int
    abroad_country: str


def my_classes(db: Session, employee: EmployeePrincipal):
    require_permission(employee, "students:read")
    return repository.teacher_classes(db, employee.employee_id)


def my_students(db: Session, employee: EmployeePrincipal, keyword: str, class_id: int | None, offset: int, limit: int):
    require_permission(employee, "students:read")
    if class_id is not None:
        classroom = repository.classroom(db, class_id)
        if classroom is None or classroom.teacher_id != employee.employee_id:
            raise BusinessError(404, "班级不存在或无权查看")
    return repository.student_directory(db, employee.student_ids, keyword, class_id, offset, limit)


def student_detail(db: Session, employee: EmployeePrincipal, student_id: int):
    require_student_scope(employee, student_id, "students:read")
    rows = repository.student_directory(db, [student_id], "", None, 0, 1)["items"]
    if not rows:
        raise BusinessError(404, "学生不存在")
    return rows[0]


def student_records(db: Session, employee: EmployeePrincipal, student_id: int, kind: str, before_id: int | None):
    require_student_scope(employee, student_id, "students:read")
    permission = "leaves:read" if kind == "leaves" else "tickets:read"
    require_permission(employee, permission)
    return repository.student_records(db, student_id, kind, before_id, employee.employee_id)


def ensure_handover_complete(db: Session, teacher_id: int):
    counts = repository.teacher_workload(db, teacher_id)
    if any(counts.values()):
        labels = {"classes": "班级", "students": "学生", "leaves": "待审批请假",
                  "tickets": "未结工单", "alerts": "未结预警", "care": "关怀个案"}
        remaining = "、".join(f"{labels[key]} {count}" for key, count in counts.items() if count)
        raise BusinessError(409, "请先完成班主任交接：" + remaining)


def placement_candidates(db, employee, keyword, offset):
    require_permission(employee, "classes:manage")
    return repository.student_directory(db, None, keyword, None, offset, 20)


def management_projects(db: Session, employee: EmployeePrincipal):
    require_permission(employee, "classes:manage")
    return repository.projects(db, enrollment_only=False)


def teachers(db: Session, employee: EmployeePrincipal, keyword: str):
    require_permission(employee, "classes:manage")
    return [dict(row) for row in teacher_options(db, keyword, 100)]


def enrollment_projects(db: Session, employee: EmployeePrincipal):
    require_permission(employee, "website-accounts:manage")
    return repository.projects(db, enrollment_only=True)


def class_list(db: Session, employee: EmployeePrincipal, project_id: int | None, *, enrollment_only: bool):
    permission = "website-accounts:manage" if enrollment_only else "classes:manage"
    require_permission(employee, permission)
    return repository.classes(db, project_id, enrollment_only=enrollment_only)


def roster(db: Session, employee: EmployeePrincipal, class_id: int):
    require_permission(employee, "classes:manage")
    if repository.classroom(db, class_id) is None:
        raise BusinessError(404, "班级不存在")
    return repository.roster(db, class_id)


def _reassign(db: Session, student_ids: list[int], previous_teacher: int, teacher_id: int):
    leaves, ticket_ids = repository.pending_teacher_work(db, student_ids, previous_teacher)
    for leave in leaves:
        leave.approver_id = teacher_id
    repository.reassign_tickets(db, ticket_ids, teacher_id)
    repository.reassign_care(db, student_ids, previous_teacher, teacher_id)
    db.flush()
    for leave in leaves:
        synchronize_source(db, "student_admin_service", leave.id)
    for ticket_id in ticket_ids:
        synchronize_source(db, "student_feedback_ticket", ticket_id)


def assign_student(db: Session, employee: EmployeePrincipal, body):
    require_permission(employee, "classes:manage")
    try:
        assignment = resolve_placement(db, body)
        result = _assign_one(db, employee, body, assignment)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def assign_students(db, employee, body):
    require_permission(employee, "classes:manage")
    ids = [row.student_id for row in body.students]
    if len(set(ids)) != len(ids):
        raise BusinessError(422, "批量名单包含重复学生")
    try:
        assignment = resolve_placement(db, body)
        results = []
        for item in sorted(body.students, key=lambda row: row.student_id):
            placement = StudentPlacementWrite(
                project_id=body.project_id, class_id=body.class_id, reason=body.reason,
                **item.model_dump(),
            )
            results.append(_assign_one(db, employee, placement, assignment))
        db.commit()
        return {"items": results, "student_count": len(results)}
    except Exception:
        db.rollback()
        raise


def _assign_one(db, employee, body, assignment):
    if not StudentAdminRepository(db).lock_student(body.student_id):
        raise BusinessError(422, f"学生{body.student_id}不存在或已停用，整批未保存")
    current = repository.enrollment(db, body.student_id)
    previous_class = current.class_id if current else None
    if previous_class != body.expected_class_id:
        raise BusinessError(409, f"学生{body.student_id}班级已变化，请刷新后核对，整批未保存")
    if previous_class == body.class_id:
        return {"student_id": body.student_id, "class_id": body.class_id, "unchanged": True}
    profile = repository.lock_student_profile(db, body.student_id)
    if profile is None:
        raise BusinessError(422, "学生缺少档案")
    if current is None:
        db.add(ClassEnrollment(student_id=body.student_id, class_id=body.class_id))
    else:
        current.class_id = body.class_id
    repository.update_student_teacher(db, [body.student_id], assignment.teacher_id, assignment.abroad_country)
    _reassign(db, [body.student_id], profile.class_teacher_id, assignment.teacher_id)
    db.add(ClassPlacementHistory(
        student_id=body.student_id, from_class_id=previous_class, to_class_id=body.class_id,
        actor_id=employee.employee_id, reason=body.reason, changed_at=utc_now(),
    ))
    AuthRepository(db).audit(employee.employee_id, "student_class_changed", body.student_id, body.model_dump())
    return {"student_id": body.student_id, "class_id": body.class_id}


def save_project(db: Session, employee: EmployeePrincipal, project_id: int, body: ProjectWrite):
    require_permission(employee, "classes:manage")
    try:
        if repository.lock_catalog_project(db, project_id) is None:
            raise BusinessError(404, "项目不存在")
        project = repository.lock_project(db, project_id)
        if project is None:
            db.add(TeachingProject(project_id=project_id, **body.model_dump()))
        else:
            if project.abroad_country != body.abroad_country and repository.project_has_students(db, project_id):
                raise BusinessError(409, "已有学生入班，不能修改项目留学地区")
            project.abroad_country = body.abroad_country
        AuthRepository(db).audit(employee.employee_id, "teaching_project_saved", project_id, body.model_dump())
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"project_id": project_id, **body.model_dump()}


def save_class(db: Session, employee: EmployeePrincipal, project_id: int, body: ClassWrite,
               class_id: int | None = None):
    require_permission(employee, "classes:manage")
    try:
        project = repository.lock_project(db, project_id)
        if project is None:
            raise BusinessError(422, "请先配置项目留学地区")
        row = repository.classroom(db, class_id, lock=True) if class_id is not None else None
        if class_id is not None and (row is None or row.project_id != project_id):
            raise BusinessError(404, "班级不存在")
        if not lock_eligible_teacher(db, body.teacher_id):
            raise BusinessError(422, "请选择可审批请假并处理学习投诉的在职员工")
        if class_id is None:
            previous_teacher_id = None
            students = []
            row = ProjectClass(project_id=project_id, **body.model_dump(exclude={"project_id"}))
            db.add(row)
        else:
            previous_teacher_id = row.teacher_id
            students = []
            if row.teacher_id != body.teacher_id:
                students = repository.class_students(db, class_id)
                repository.update_student_teacher(db, students, body.teacher_id, project.abroad_country)
                _reassign(db, students, row.teacher_id, body.teacher_id)
            row.name = body.name
            row.teacher_id = body.teacher_id
            row.enabled = body.enabled
        db.flush()
        result = {"id": row.id, "project_id": row.project_id, "name": row.name,
                  "teacher_id": row.teacher_id, "enabled": row.enabled}
        AuthRepository(db).audit(employee.employee_id, "project_class_saved", row.id, {
            **result, "previous_teacher_id": previous_teacher_id, "transferred_student_ids": students,
        })
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessError(409, "该项目已有同名班级") from exc
    except Exception:
        db.rollback()
        raise
    return result


def edit_class(db: Session, employee: EmployeePrincipal, class_id: int, body: ClassWrite):
    require_permission(employee, "classes:manage")
    row = repository.classroom(db, class_id)
    if row is None:
        raise BusinessError(404, "班级不存在")
    return save_class(db, employee, row.project_id, body, class_id)


def resolve_placement(db: Session, body: ClassPlacement) -> ClassAssignment:
    catalog = repository.lock_catalog_project(db, body.project_id)
    project = repository.lock_project(db, body.project_id) if catalog and catalog.status == 1 else None
    if project is None:
        raise BusinessError(422, "请选择开放且已配置留学地区的项目")
    row = repository.classroom(db, body.class_id, lock=True)
    if row is None or row.project_id != body.project_id or not row.enabled:
        raise BusinessError(422, "请选择该项目下可入班的班级")
    if not lock_eligible_teacher(db, row.teacher_id):
        raise BusinessError(409, "班主任当前不可用，请在班级管理中核对")
    return ClassAssignment(row.id, row.teacher_id, project.abroad_country)


def place_student(db: Session, student_id: int, placement: ClassPlacement, assignment: ClassAssignment):
    if assignment.class_id != placement.class_id:
        raise BusinessError(422, "入班信息不一致，请重新选择班级")
    current = repository.enrollment(db, student_id)
    if current is not None:
        if current.class_id != placement.class_id:
            raise BusinessError(409, "该学生已在其他班级，请核对现有学籍")
        return
    profile = repository.lock_student_profile(db, student_id)
    if profile is None:
        raise BusinessError(422, "该学生缺少档案，无法入班")
    db.add(ClassEnrollment(student_id=student_id, class_id=placement.class_id))
    repository.update_student_teacher(db, [student_id], assignment.teacher_id, assignment.abroad_country)
    _reassign(db, [student_id], profile.class_teacher_id, assignment.teacher_id)
