from app.core.exceptions import BusinessError
from app.core.security.authorization import require_permission, require_student_scope
from app.modules.auth.repository import AuthRepository
from app.modules.classroom import repository as classrooms
from . import repository
from .models import TeachingCourse


def view(row):
    return {"id": row.id, "name": row.name, "study_stage": row.study_stage,
            "institution": row.institution, "enabled": row.enabled}


def list_courses(db, principal, keyword):
    require_permission(principal, "teaching:manage")
    return [view(row) for row in repository.list_courses(db, keyword)]


def save_course(db, principal, body, course_id=None):
    require_permission(principal, "teaching:manage")
    try:
        row = repository.course(db, course_id, lock=True) if course_id else TeachingCourse()
        if row is None:
            raise BusinessError(404, "课程不存在")
        for key, value in body.model_dump().items():
            setattr(row, key, value)
        db.add(row)
        db.flush()
        result = view(row)
        AuthRepository(db).audit(principal.employee_id, "teaching_course_saved", row.id, result)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def class_courses(db, principal, class_id):
    require_permission(principal, "teaching:manage")
    if classrooms.classroom(db, class_id) is None:
        raise BusinessError(404, "班级不存在")
    return repository.assigned_ids(db, class_id)


def assign_courses(db, principal, class_id, body):
    require_permission(principal, "teaching:manage")
    ids = set(body.course_ids)
    if any(type(course_id) is not int or course_id < 1 for course_id in ids):
        raise BusinessError(422, "课程编号须为正整数")
    try:
        if classrooms.classroom(db, class_id, lock=True) is None:
            raise BusinessError(404, "班级不存在")
        for course_id in sorted(ids):
            if repository.course(db, course_id, lock=True) is None:
                raise BusinessError(422, "包含不存在的课程")
        repository.replace_assignments(db, class_id, ids)
        AuthRepository(db).audit(principal.employee_id, "class_courses_saved", class_id, {"course_ids": sorted(ids)})
        db.commit()
        return {"class_id": class_id, "course_ids": sorted(ids)}
    except Exception:
        db.rollback()
        raise


def student_courses(db, principal, student_id):
    require_student_scope(principal, student_id, "scores:read")
    return [view(row) for row in repository.student_courses(db, student_id)]


def score_course(db, student_id, course_id, *, existing_course_id=None):
    if course_id == existing_course_id:
        row = repository.course(db, course_id)
    else:
        row = next((row for row in repository.student_courses(db, student_id) if row.id == course_id), None)
    if row is None:
        raise BusinessError(422, "请选择该学生班级已安排的有效课程")
    return row


def named_score_course(db, student_id, name, study_stage):
    """Legacy/AI callers can use a name, but cannot invent a class course."""
    if classrooms.enrollment(db, student_id) is None:
        return None
    choices = [row for row in repository.student_courses(db, student_id)
               if row.name == name and (study_stage == "unspecified" or row.study_stage == study_stage)]
    if len(choices) != 1:
        raise BusinessError(422, "请从管理员安排的班级课程中选择，重名课程需提供课程编号")
    return choices[0]
