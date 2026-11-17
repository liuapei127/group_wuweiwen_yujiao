from sqlalchemy import func, inspect, select, update
from sqlalchemy.orm import Session

from app.modules.auth.repository import student_info
from app.modules.auth.models import accounts
from app.modules.feedback.models import student_feedback_ticket
from app.modules.student_admin.models import StudentAdminService, SysUser
from app.modules.visitor.catalog import _courses
from app.modules.statistics.wellbeing_models import WellbeingCase
from app.modules.student.alerts import _alert

from .models import ClassEnrollment, ProjectClass, TeachingProject


def projects(db: Session, *, enrollment_only: bool):
    if enrollment_only:
        stmt = (
            select(_courses.c.id, _courses.c.project_name, TeachingProject.abroad_country)
            .join(TeachingProject, TeachingProject.project_id == _courses.c.id)
            .where(_courses.c.status == 1)
            .where(select(ProjectClass.id).join(SysUser, SysUser.id == ProjectClass.teacher_id).where(
                ProjectClass.project_id == _courses.c.id, ProjectClass.enabled.is_(True),
                SysUser.status == "normal", SysUser.user_type == "employee",
            ).exists())
        )
    else:
        stmt = (
            select(_courses.c.id, _courses.c.project_name, _courses.c.status,
                   TeachingProject.abroad_country)
            .outerjoin(TeachingProject, TeachingProject.project_id == _courses.c.id)
        )
    return [dict(row) for row in db.execute(stmt.order_by(_courses.c.project_name, _courses.c.id)).mappings()]


def lock_catalog_project(db: Session, project_id: int):
    return db.execute(select(_courses.c.id, _courses.c.status).where(
        _courses.c.id == project_id,
    ).with_for_update()).one_or_none()


def lock_project(db: Session, project_id: int):
    return db.scalar(select(TeachingProject).where(
        TeachingProject.project_id == project_id,
    ).with_for_update().execution_options(populate_existing=True))


def classroom(db: Session, class_id: int, *, lock: bool = False):
    stmt = select(ProjectClass).where(ProjectClass.id == class_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def classes(db: Session, project_id: int | None, *, enrollment_only: bool):
    stmt = select(
        ProjectClass.id, ProjectClass.project_id, ProjectClass.name, ProjectClass.enabled,
        ProjectClass.teacher_id, SysUser.real_name.label("teacher_name"),
        _courses.c.project_name,
    ).join(SysUser, SysUser.id == ProjectClass.teacher_id).join(_courses, _courses.c.id == ProjectClass.project_id)
    if enrollment_only:
        stmt = stmt.where(
            _courses.c.status == 1, ProjectClass.enabled.is_(True),
            SysUser.status == "normal", SysUser.user_type == "employee",
        )
    else:
        count = select(func.count()).where(ClassEnrollment.class_id == ProjectClass.id).scalar_subquery()
        stmt = stmt.add_columns(count.label("student_count"))
    if project_id is not None:
        stmt = stmt.where(ProjectClass.project_id == project_id)
    return [dict(row) for row in db.execute(stmt.order_by(ProjectClass.name, ProjectClass.id)).mappings()]


def roster(db: Session, class_id: int):
    stmt = (
        select(SysUser.id, SysUser.real_name, student_info.c.student_no)
        .join(ClassEnrollment, ClassEnrollment.student_id == SysUser.id)
        .join(student_info, student_info.c.user_id == SysUser.id)
        .where(ClassEnrollment.class_id == class_id)
        .order_by(SysUser.real_name, SysUser.id)
    )
    return [dict(row) for row in db.execute(stmt).mappings()]


def enrollment(db: Session, student_id: int):
    return db.get(ClassEnrollment, student_id, with_for_update=True)


def class_students(db: Session, class_id: int):
    stmt = select(ClassEnrollment.student_id).where(ClassEnrollment.class_id == class_id)
    return list(db.scalars(stmt.order_by(ClassEnrollment.student_id).with_for_update()))


def project_has_students(db: Session, project_id: int):
    stmt = select(ClassEnrollment.student_id).join(ProjectClass).where(ProjectClass.project_id == project_id).limit(1)
    return db.scalar(stmt) is not None


def lock_student_profile(db: Session, student_id: int):
    return db.execute(select(student_info.c.user_id, student_info.c.class_teacher_id).where(
        student_info.c.user_id == student_id,
    ).with_for_update()).one_or_none()


def update_student_teacher(db: Session, student_ids: list[int], teacher_id: int, abroad_country: str):
    db.execute(update(student_info).where(student_info.c.user_id.in_(student_ids)).values(
        class_teacher_id=teacher_id, abroad_country=abroad_country,
    ))


def pending_teacher_work(db: Session, student_ids: list[int], teacher_id: int):
    leaves = db.scalars(select(StudentAdminService).where(
        StudentAdminService.student_id.in_(student_ids),
        StudentAdminService.service_type == "leave", StudentAdminService.status == "pending",
    ).order_by(StudentAdminService.id).with_for_update()).all()
    tickets = student_feedback_ticket
    ticket_ids = db.scalars(select(tickets.c.id).where(
        tickets.c.student_id.in_(student_ids),
        tickets.c.category == "learning", tickets.c.status.in_(("pending", "processing")),
    ).order_by(tickets.c.id).with_for_update()).all()
    return leaves, ticket_ids


def reassign_tickets(db: Session, ticket_ids: list[int], teacher_id: int):
    if ticket_ids:
        db.execute(update(student_feedback_ticket).where(
            student_feedback_ticket.c.id.in_(ticket_ids),
        ).values(assignee_id=teacher_id))


def reassign_care(db: Session, student_ids, previous_teacher: int, teacher_id: int):
    if not student_ids:
        return
    db.execute(update(_alert).where(
        _alert.c.student_id.in_(student_ids),
        _alert.c.status.in_(("pending", "following")),
    ).values(teacher_id=teacher_id))
    db.execute(update(WellbeingCase).where(
        WellbeingCase.student_id.in_(student_ids),
        WellbeingCase.status.in_(("open", "following")),
    ).values(assigned_to=teacher_id))


def teacher_workload(db: Session, teacher_id: int):
    definitions = (
        ("classes", ProjectClass.__table__, ProjectClass.teacher_id == teacher_id),
        ("students", student_info, student_info.c.class_teacher_id == teacher_id),
        ("leaves", StudentAdminService.__table__,
         (StudentAdminService.approver_id == teacher_id) & (StudentAdminService.status == "pending")),
        ("tickets", student_feedback_ticket,
         (student_feedback_ticket.c.assignee_id == teacher_id) & (student_feedback_ticket.c.category == "learning") & student_feedback_ticket.c.status.in_(("pending", "processing"))),
        ("alerts", _alert, (_alert.c.teacher_id == teacher_id) & _alert.c.status.in_(("pending", "following"))),
        ("care", WellbeingCase.__table__,
         (WellbeingCase.assigned_to == teacher_id) & WellbeingCase.status.in_(("open", "following"))),
    )
    result = {}
    for key, table, condition in definitions:
        if inspect(db.connection()).has_table(table.name):
            result[key] = db.scalar(select(func.count()).select_from(table).where(condition))
    return result


def teacher_classes(db: Session, teacher_id: int):
    count = select(func.count()).where(ClassEnrollment.class_id == ProjectClass.id).scalar_subquery()
    stmt = select(
        ProjectClass.id, ProjectClass.name, ProjectClass.project_id, ProjectClass.enabled,
        _courses.c.project_name, TeachingProject.abroad_country, count.label("student_count"),
    ).join(TeachingProject).join(_courses, _courses.c.id == ProjectClass.project_id).where(
        ProjectClass.teacher_id == teacher_id,
    ).order_by(_courses.c.project_name, ProjectClass.name, ProjectClass.id)
    return [dict(row) for row in db.execute(stmt).mappings()]


def student_directory(db: Session, student_ids, keyword: str, class_id: int | None, offset: int, limit: int):
    stmt = select(
        accounts.c.id, accounts.c.real_name, accounts.c.contact_info, accounts.c.status,
        student_info.c.student_no, student_info.c.school, student_info.c.major,
        student_info.c.abroad_country, student_info.c.class_teacher_id,
        ProjectClass.id.label("class_id"), ProjectClass.name.label("class_name"),
        ProjectClass.project_id, _courses.c.project_name,
    ).select_from(accounts).outerjoin(student_info, student_info.c.user_id == accounts.c.id).outerjoin(
        ClassEnrollment, ClassEnrollment.student_id == accounts.c.id,
    ).outerjoin(ProjectClass, ProjectClass.id == ClassEnrollment.class_id).outerjoin(
        _courses, _courses.c.id == ProjectClass.project_id,
    ).where(accounts.c.user_type == "student")
    if student_ids is not None:
        stmt = stmt.where(accounts.c.id.in_(student_ids))
    if class_id is not None:
        stmt = stmt.where(ProjectClass.id == class_id)
    if keyword:
        stmt = stmt.where(accounts.c.real_name.contains(keyword, autoescape=True) |
                          student_info.c.student_no.contains(keyword, autoescape=True))
    rows = list(db.execute(stmt.order_by(accounts.c.real_name, accounts.c.id).offset(offset).limit(limit + 1)).mappings())
    return {"items": [dict(row) for row in rows[:limit]], "has_more": len(rows) > limit}


def student_records(db: Session, student_id: int, kind: str, before_id: int | None):
    if kind == "leaves":
        columns = StudentAdminService.__table__.c
        filters = [columns.student_id == student_id, columns.service_type == "leave"]
    else:
        columns = student_feedback_ticket.c
        filters = [columns.student_id == student_id, columns.category == "learning"]
    stmt = select(*columns).where(*filters)
    if before_id is not None:
        stmt = stmt.where(columns.id < before_id)
    rows = list(db.execute(stmt.order_by(columns.id.desc()).limit(21)).mappings())
    return {"items": [dict(row) for row in rows[:20]], "has_more": len(rows) > 20}
