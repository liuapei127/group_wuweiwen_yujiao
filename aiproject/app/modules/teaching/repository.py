from sqlalchemy import delete, select

from app.modules.classroom.models import ClassEnrollment
from .models import ClassCourse, TeachingCourse


def course(db, course_id, *, lock=False):
    stmt = select(TeachingCourse).where(TeachingCourse.id == course_id)
    if lock:
        stmt = stmt.with_for_update().execution_options(populate_existing=True)
    return db.scalar(stmt)


def list_courses(db, keyword):
    stmt = select(TeachingCourse)
    if keyword:
        stmt = stmt.where(TeachingCourse.name.contains(keyword, autoescape=True))
    return list(db.scalars(stmt.order_by(TeachingCourse.name, TeachingCourse.id)))


def assigned_ids(db, class_id):
    return list(db.scalars(select(ClassCourse.course_id).where(ClassCourse.class_id == class_id)))


def replace_assignments(db, class_id, course_ids):
    db.execute(delete(ClassCourse).where(ClassCourse.class_id == class_id))
    db.add_all([ClassCourse(class_id=class_id, course_id=course_id) for course_id in sorted(course_ids)])


def student_courses(db, student_id):
    stmt = select(TeachingCourse).join(ClassCourse).join(
        ClassEnrollment, ClassEnrollment.class_id == ClassCourse.class_id,
    ).where(ClassEnrollment.student_id == student_id, TeachingCourse.enabled.is_(True))
    return list(db.scalars(stmt.order_by(TeachingCourse.study_stage, TeachingCourse.name, TeachingCourse.id)))
