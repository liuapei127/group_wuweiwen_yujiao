import hashlib
import re
from dataclasses import dataclass
from datetime import timedelta
from secrets import token_hex, token_urlsafe

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.security import EmployeePrincipal
from app.core.security.authorization import require_permission
from app.modules.auth.repository import AuthRepository
from app.modules.auth.schemas import PasswordReset
from app.modules.student_admin.repository import StudentAdminRepository
from app.core.security.credentials import hash_password, utc_now, verify_password

from . import repository
from .models import VisitorAccount, VisitorSession, WebsiteStudentAccess
from .schemas import VisitorLogin, VisitorRegister, VisitorToken, WebsiteAccountOut, WebsiteStudentCreate, WebsiteStudentUpdate

_SESSION_SECONDS = 3600
_TOKEN_PATTERN = re.compile(r"visitor_[0-9a-f]{64}")


@dataclass(frozen=True)
class VisitorPrincipal:
    visitor_id: int
    digest: str


def register(db: Session, payload: VisitorRegister) -> VisitorToken:
    account = VisitorAccount(
        username=payload.username, name=payload.name, contact=payload.contact,
        password_hash=hash_password(payload.password), created_at=utc_now(),
    )
    try:
        db.add(account)
        db.flush()
        reply = _issue_session(db, account.id)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if repository.account_by_username(db, payload.username):
            raise BusinessError(409, "用户名已被使用") from exc
        raise
    except Exception:
        db.rollback()
        raise
    return reply


def login(db: Session, payload: VisitorLogin) -> VisitorToken:
    account = repository.account_by_username(db, payload.username)
    initial_hash = account.password_hash if account else None
    if not verify_password(payload.password, initial_hash) or account is None:
        raise BusinessError(401, "用户名或密码不正确")
    try:
        locked = repository.lock_website_account(db, account.id)
        if locked is None or (
            locked.password_hash != initial_hash and not verify_password(payload.password, locked.password_hash)
        ):
            raise BusinessError(401, "用户名或密码不正确")
        repository.delete_expired_for_visitor(db, locked.id, utc_now())
        access = repository.student_access(db, locked.id, lock=True)
        student = bool(access and access.enabled and StudentAdminRepository(db).lock_student(access.student_id))
        reply = _issue_session(db, locked.id, student=student)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return reply


def authenticate(db: Session, token: str) -> VisitorPrincipal | None:
    if not _TOKEN_PATTERN.fullmatch(token):
        return None
    digest = _digest(token)
    visitor_id = repository.session_visitor(db, digest, utc_now())
    return VisitorPrincipal(visitor_id, digest) if visitor_id is not None else None


def logout(db: Session, principal: VisitorPrincipal) -> None:
    try:
        repository.delete_session(db, principal.digest)
        db.commit()
    except Exception:
        db.rollback()
        raise


def _issue_session(db: Session, visitor_id: int, *, student: bool = False) -> VisitorToken:
    token = "visitor_" + token_hex(32)
    db.add(VisitorSession(
        visitor_id=visitor_id, digest=_digest(token),
        expires_at=utc_now() + timedelta(seconds=_SESSION_SECONDS),
    ))
    return VisitorToken(access_token=token, expires_in=_SESSION_SECONDS, account_type="student" if student else "visitor")


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("ascii")).hexdigest()


def list_accounts(
    db: Session, employee: EmployeePrincipal, keyword: str, after_id: int, limit: int
) -> list[WebsiteAccountOut]:
    require_permission(employee, "website-accounts:manage")
    return [_website_account(account, access) for account, access in
            repository.list_website_accounts(db, keyword, after_id, limit)]


def reset_website_password(
    db: Session, employee: EmployeePrincipal, visitor_id: int, payload: PasswordReset
) -> dict[str, int | bool]:
    require_permission(employee, "website-accounts:manage")
    try:
        account = repository.lock_website_account(db, visitor_id)
        if account is None:
            raise BusinessError(404, "官网账号不存在")
        account.password_hash = hash_password(payload.new_password)
        repository.delete_website_sessions(db, visitor_id)
        AuthRepository(db).audit(employee.employee_id, "website_password_reset", visitor_id)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"id": visitor_id, "sessions_revoked": True}


def change_student_access(
    db: Session, employee: EmployeePrincipal, visitor_id: int, payload: WebsiteStudentUpdate
) -> WebsiteAccountOut:
    require_permission(employee, "website-accounts:manage")
    try:
        account = repository.lock_website_account(db, visitor_id)
        if account is None:
            raise BusinessError(404, "官网账号不存在")
        access = repository.student_access(db, visitor_id, lock=True)
        if access is not None and access.student_id != payload.student_id:
            raise BusinessError(409, "该官网账号已绑定其他学籍")
        if access is None and not payload.enabled:
            raise BusinessError(409, "该官网账号尚未绑定学籍")
        if payload.enabled and not StudentAdminRepository(db).lock_student(payload.student_id):
            raise BusinessError(422, "请选择有效的企业学生档案")
        if access is None or access.enabled != payload.enabled:
            if access is None:
                access = WebsiteStudentAccess(visitor_id=visitor_id, student_id=payload.student_id, enabled=True)
                db.add(access)
            else:
                access.enabled = payload.enabled
            db.flush()
            _record_student_access(db, employee, access)
        result = _website_account(account, access)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessError(409, "该学籍已绑定其他官网账号") from exc
    except Exception:
        db.rollback()
        raise
    return result


def _website_account(account: VisitorAccount, access: WebsiteStudentAccess | None) -> WebsiteAccountOut:
    return WebsiteAccountOut(
        id=account.id, username=account.username, name=account.name, contact=account.contact,
        created_at=account.created_at, student_id=access.student_id if access else None,
        student_enabled=access.enabled if access else False,
    )


def website_student(db: Session, principal: VisitorPrincipal, *, lock: bool = False) -> int | None:
    if lock:
        repository.lock_website_account(db, principal.visitor_id)
        if repository.session_visitor(db, principal.digest, utc_now(), lock=True) != principal.visitor_id:
            raise BusinessError(401, "请重新登录官网")
    return repository.active_student_id(db, principal.visitor_id, lock=lock)


def list_students(db: Session, employee: EmployeePrincipal, keyword: str, limit: int):
    require_permission(employee, "website-accounts:manage")
    return [dict(row) for row in repository.student_options(db, keyword, limit)]


def create_and_enable_student(
    db: Session, employee: EmployeePrincipal, visitor_id: int, payload: WebsiteStudentCreate
) -> WebsiteAccountOut:
    require_permission(employee, "website-accounts:manage")
    try:
        account = repository.lock_website_account(db, visitor_id)
        if account is None:
            raise BusinessError(404, "官网账号不存在")
        if repository.student_access(db, visitor_id, lock=True) is not None:
            raise BusinessError(409, "该官网账号已有学籍，请在现有绑定上管理学生身份")
        if not repository.lock_eligible_teacher(db, payload.class_teacher_id):
            raise BusinessError(422, "请选择可审批请假并处理学习投诉的在职员工")
        student_role = repository.active_student_role_id(db)
        if student_role is None:
            raise BusinessError(409, "企业的学生角色尚未启用")
        student_id = AuthRepository(db).create_account({
            "username": f"website-student-{visitor_id}-{token_hex(8)}",
            "password_hash": hash_password(token_urlsafe(32)),
            "real_name": account.name,
            "contact_info": account.contact,
            "user_type": "student",
            "role_id": student_role,
            "status": "normal",
            "create_time": utc_now(),
            "update_time": utc_now(),
        })
        repository.create_student_profile(db, student_id, payload.class_teacher_id, payload.abroad_country)
        access = WebsiteStudentAccess(visitor_id=visitor_id, student_id=student_id, enabled=True)
        db.add(access)
        db.flush()
        _record_student_access(db, employee, access, class_teacher_id=payload.class_teacher_id,
                               abroad_country=payload.abroad_country)
        result = _website_account(account, access)
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessError(409, "学生档案保存冲突，请刷新官网账号后核对") from exc
    except Exception:
        db.rollback()
        raise
    return result


def list_teachers(db: Session, employee: EmployeePrincipal, keyword: str, limit: int):
    require_permission(employee, "website-accounts:manage")
    return [dict(row) for row in repository.teacher_options(db, keyword, limit)]


def _record_student_access(
    db: Session, employee: EmployeePrincipal, access: WebsiteStudentAccess, **details
) -> None:
    repository.delete_website_sessions(db, access.visitor_id)
    AuthRepository(db).audit(employee.employee_id, "website_student_access", access.visitor_id, {
        "student_id": access.student_id, "enabled": access.enabled, **details,
    })
