from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.exceptions import BusinessError
from app.core.responses import success
from app.core.security import EmployeePrincipal, require_employee
from app.modules.auth.schemas import PasswordReset
from app.modules.customer_service.capacity import CsCapacityExceeded, CsChatCapacity

from app.shared.constants.study_policies import study_policies

from . import service
from .catalog import CourseWrite, list_courses, save_course, staff_courses
from .schemas import VisitorLogin, VisitorRegister, WebsiteIdentity, WebsiteStudentCreate, WebsiteStudentUpdate

router = APIRouter(prefix="/api/v1/visitors", tags=["官网游客"])
Database = Annotated[Session, Depends(get_db)]
_BEARER = HTTPBearer(auto_error=False)
_AUTH_CAPACITY = CsChatCapacity(4, 2, 10)


def require_visitor(
    db: Database, credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_BEARER)]
) -> service.VisitorPrincipal:
    principal = service.authenticate(db, credentials.credentials) if credentials else None
    if principal is None:
        raise HTTPException(401, "请先登录官网", headers={"WWW-Authenticate": "Bearer"})
    return principal


Principal = Annotated[service.VisitorPrincipal, Depends(require_visitor)]


async def _authenticate_request(request: Request, operation, db: Session, payload):
    client_ip = request.client.host if request.client else "unknown"
    try:
        async with _AUTH_CAPACITY.slot(client_ip):
            return success(await run_in_threadpool(operation, db, payload))
    except CsCapacityExceeded as exc:
        raise BusinessError(429, exc.message) from exc


@router.post("/register", status_code=201)
async def register(body: VisitorRegister, db: Database, request: Request):
    return await _authenticate_request(request, service.register, db, body)


@router.post("/login")
async def login(body: VisitorLogin, db: Database, request: Request):
    return await _authenticate_request(request, service.login, db, body)


@router.post("/logout")
def logout(db: Database, principal: Principal):
    service.logout(db, principal)
    return success()


@router.get("/me")
def me(db: Database, principal: Principal):
    student_id = service.website_student(db, principal)
    return success(WebsiteIdentity(account_type="student" if student_id is not None else "visitor"))


@router.get("/policies")
def policies(principal: Principal, country: Literal["Singapore", "Germany"]):
    return success(study_policies(country))


@router.get("/courses")
def courses(
    db: Database, principal: Principal, keyword: Annotated[str, Query(max_length=64)] = "",
    after_id: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return success(list_courses(db, keyword.strip(), after_id, limit))


staff_router = APIRouter(prefix="/api/v1/enterprise/website-accounts", tags=["官网账号管理"])
Employee = Annotated[EmployeePrincipal, Depends(require_employee)]


@staff_router.get("")
def list_accounts(
    db: Database, employee: Employee, keyword: Annotated[str, Query(max_length=64)] = "",
    after_id: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return success(service.list_accounts(db, employee, keyword.strip(), after_id, limit))


@staff_router.post("/{visitor_id}/password")
def reset_password(visitor_id: int, payload: PasswordReset, db: Database, employee: Employee):
    return success(service.reset_website_password(db, employee, visitor_id, payload))


@staff_router.get("/students")
def student_options(
    db: Database, employee: Employee, keyword: Annotated[str, Query(max_length=64)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return success(service.list_students(db, employee, keyword.strip(), limit))


@staff_router.put("/{visitor_id}/student-access")
def update_student_access(visitor_id: int, payload: WebsiteStudentUpdate, db: Database, employee: Employee):
    return success(service.change_student_access(db, employee, visitor_id, payload))


@staff_router.get("/teachers")
def teacher_options(
    db: Database, employee: Employee, keyword: Annotated[str, Query(max_length=64)] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
):
    return success(service.list_teachers(db, employee, keyword.strip(), limit))


@staff_router.post("/{visitor_id}/student-access", status_code=201)
def create_student_access(visitor_id: int, payload: WebsiteStudentCreate, db: Database, employee: Employee):
    return success(service.create_and_enable_student(db, employee, visitor_id, payload))


course_router = APIRouter(prefix="/api/v1/enterprise/courses", tags=["课程管理"])


@course_router.get("")
def catalog(
    db: Database, employee: Employee, keyword: Annotated[str, Query(max_length=64)] = "",
    after_id: Annotated[int, Query(ge=0)] = 0, limit: Annotated[int, Query(ge=1, le=50)] = 20,
):
    return success(staff_courses(db, keyword.strip(), after_id, limit))


@course_router.post("", status_code=201)
def create_course(body: CourseWrite, db: Database, employee: Employee):
    return success(save_course(db, body))


@course_router.put("/{course_id}")
def update_course(course_id: int, body: CourseWrite, db: Database, employee: Employee):
    return success(save_course(db, body, course_id))
