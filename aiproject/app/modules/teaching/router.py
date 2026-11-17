from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import success
from app.core.security import EmployeePrincipal, require_employee
from . import service
from .schemas import ClassCoursesWrite, CourseWrite

router = APIRouter(prefix="/api/v1/teaching", tags=["教学课程"])
Database = Annotated[Session, Depends(get_db)]
Staff = Annotated[EmployeePrincipal, Depends(require_employee)]


@router.get("/courses")
def courses(db: Database, staff: Staff, keyword: Annotated[str, Query(max_length=64)] = ""):
    return success(service.list_courses(db, staff, keyword.strip()))


@router.post("/courses", status_code=201)
def create(body: CourseWrite, db: Database, staff: Staff):
    return success(service.save_course(db, staff, body))


@router.put("/courses/{course_id}")
def update(course_id: int, body: CourseWrite, db: Database, staff: Staff):
    return success(service.save_course(db, staff, body, course_id))


@router.get("/classes/{class_id}/courses")
def class_courses(class_id: int, db: Database, staff: Staff):
    return success(service.class_courses(db, staff, class_id))


@router.put("/classes/{class_id}/courses")
def assign(class_id: int, body: ClassCoursesWrite, db: Database, staff: Staff):
    return success(service.assign_courses(db, staff, class_id, body))


@router.get("/students/{student_id}/courses")
def student_courses(student_id: int, db: Database, staff: Staff):
    return success(service.student_courses(db, staff, student_id))
