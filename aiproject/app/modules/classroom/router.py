from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import success
from app.core.security import EmployeePrincipal, require_employee

from . import service
from .schemas import ClassCreate, ClassWrite, ProjectWrite, StudentPlacementWrite, StudentPlacementBatch

router = APIRouter(prefix="/api/v1/enterprise/classrooms", tags=["班级与老师管理"])
teacher_router = APIRouter(prefix="/api/v1/teacher", tags=["班主任学生事务"])
Database = Annotated[Session, Depends(get_db)]
Employee = Annotated[EmployeePrincipal, Depends(require_employee)]


@teacher_router.get("/classes")
def my_classes(db: Database, employee: Employee):
    return success(service.my_classes(db, employee))


@teacher_router.get("/students")
def my_students(
    db: Database, employee: Employee, keyword: Annotated[str, Query(max_length=64)] = "",
    class_id: Annotated[int | None, Query(gt=0)] = None,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
):
    return success(service.my_students(db, employee, keyword.strip(), class_id, offset, limit))


@teacher_router.get("/students/{student_id}")
def student_detail(student_id: int, db: Database, employee: Employee):
    return success(service.student_detail(db, employee, student_id))


@teacher_router.get("/students/{student_id}/records/{kind}")
def student_records(
    student_id: int, kind: Literal["leaves", "complaints"], db: Database, employee: Employee,
    before_id: Annotated[int | None, Query(gt=0)] = None,
):
    return success(service.student_records(db, employee, student_id, kind, before_id))


@router.get("/projects")
def projects(db: Database, employee: Employee):
    return success(service.management_projects(db, employee))


@router.post("/student-placements")
def assign_student(body: StudentPlacementWrite, db: Database, employee: Employee):
    return success(service.assign_student(db, employee, body))


@router.post("/student-placements/batch")
def assign_students(body: StudentPlacementBatch, db: Database, employee: Employee):
    return success(service.assign_students(db, employee, body))


@router.get("/students")
def placement_candidates(
    db: Database, employee: Employee, keyword: Annotated[str, Query(max_length=64)] = "",
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
):
    return success(service.placement_candidates(db, employee, keyword.strip(), offset))


@router.get("/teachers")
def teachers(db: Database, employee: Employee, keyword: Annotated[str, Query(max_length=64)] = ""):
    return success(service.teachers(db, employee, keyword.strip()))


@router.put("/projects/{project_id}")
def project_settings(project_id: int, payload: ProjectWrite, db: Database, employee: Employee):
    return success(service.save_project(db, employee, project_id, payload))


@router.get("/enrollment-projects")
def enrollment_projects(db: Database, employee: Employee):
    return success(service.enrollment_projects(db, employee))


@router.get("/enrollment-projects/{project_id}/classes")
def enrollment_classes(project_id: int, db: Database, employee: Employee):
    return success(service.class_list(db, employee, project_id, enrollment_only=True))


@router.get("")
def classes(db: Database, employee: Employee, project_id: Annotated[int | None, Query(gt=0)] = None):
    return success(service.class_list(db, employee, project_id, enrollment_only=False))


@router.post("", status_code=201)
def create(payload: ClassCreate, db: Database, employee: Employee):
    return success(service.save_class(db, employee, payload.project_id, payload))


@router.put("/{class_id}")
def update(class_id: int, payload: ClassWrite, db: Database, employee: Employee):
    return success(service.edit_class(db, employee, class_id, payload))


@router.get("/{class_id}/students")
def students(class_id: int, db: Database, employee: Employee):
    return success(service.roster(db, employee, class_id))
