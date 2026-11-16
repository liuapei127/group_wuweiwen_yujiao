from datetime import datetime

from sqlalchemy import delete, insert, or_, select
from sqlalchemy.orm import Session

from app.modules.auth.models import accounts, role_permissions, roles
from app.modules.auth.repository import student_info
from app.modules.student_admin.models import SysUser

from .models import VisitorAccount, VisitorAvatar, VisitorSession, WebsiteStudentAccess


def profile_account(db: Session, visitor_id: int) -> VisitorAccount | None:
    return db.get(VisitorAccount, visitor_id)


def avatar_bytes(db: Session, visitor_id: int) -> bytes | None:
    return db.scalar(select(VisitorAvatar.image).where(VisitorAvatar.visitor_id == visitor_id))


def save_avatar(db: Session, visitor_id: int, image: bytes) -> None:
    avatar = db.get(VisitorAvatar, visitor_id)
    if avatar is None:
        db.add(VisitorAvatar(visitor_id=visitor_id, image=image))
    else:
        avatar.image = image


def account_by_username(db: Session, username: str) -> VisitorAccount | None:
    return db.scalar(select(VisitorAccount).where(VisitorAccount.username == username))


def session_visitor(db: Session, digest: str, now: datetime, *, lock: bool = False) -> int | None:
    stmt = (
        select(VisitorSession.visitor_id)
        .join(VisitorAccount)
        .where(VisitorSession.digest == digest, VisitorSession.expires_at > now)
    )
    return db.scalar(stmt.with_for_update() if lock else stmt)


def delete_session(db: Session, digest: str) -> None:
    db.execute(delete(VisitorSession).where(VisitorSession.digest == digest))


def delete_expired_for_visitor(db: Session, visitor_id: int, now: datetime) -> None:
    db.execute(delete(VisitorSession).where(
        VisitorSession.visitor_id == visitor_id, VisitorSession.expires_at <= now
    ))


def student_access(db: Session, visitor_id: int, *, lock: bool = False) -> WebsiteStudentAccess | None:
    query = select(WebsiteStudentAccess).where(WebsiteStudentAccess.visitor_id == visitor_id)
    return db.scalar(query.with_for_update() if lock else query)


def lock_website_account(db: Session, visitor_id: int) -> VisitorAccount | None:
    stmt = select(VisitorAccount).where(VisitorAccount.id == visitor_id).with_for_update()
    return db.scalar(stmt.execution_options(populate_existing=True))


def active_student_id(db: Session, visitor_id: int, *, lock: bool = False) -> int | None:
    stmt = (
        select(SysUser.id).join(WebsiteStudentAccess, WebsiteStudentAccess.student_id == SysUser.id)
        .where(
            WebsiteStudentAccess.visitor_id == visitor_id, WebsiteStudentAccess.enabled.is_(True),
            SysUser.user_type == "student", SysUser.status == "normal",
        )
    )
    return db.scalar(stmt.with_for_update() if lock else stmt)


def delete_website_sessions(db: Session, visitor_id: int) -> None:
    db.execute(delete(VisitorSession).where(VisitorSession.visitor_id == visitor_id))


def list_website_accounts(db: Session, keyword: str, after_id: int, limit: int):
    stmt = (
        select(VisitorAccount, WebsiteStudentAccess)
        .outerjoin(WebsiteStudentAccess, WebsiteStudentAccess.visitor_id == VisitorAccount.id)
        .where(VisitorAccount.id > after_id)
        .order_by(VisitorAccount.id)
        .limit(limit)
    )
    if keyword:
        stmt = stmt.where(or_(
            VisitorAccount.username.contains(keyword, autoescape=True),
            VisitorAccount.name.contains(keyword, autoescape=True),
        ))
    return db.execute(stmt).all()


def student_options(db: Session, keyword: str, limit: int):
    stmt = select(SysUser.id, SysUser.real_name).where(SysUser.user_type == "student", SysUser.status == "normal")
    if keyword:
        stmt = stmt.where(SysUser.real_name.contains(keyword, autoescape=True))
    return db.execute(stmt.order_by(SysUser.id).limit(limit)).mappings().all()


def active_student_role_id(db: Session) -> int | None:
    stmt = select(roles.c.id).where(roles.c.role_code == "student", roles.c.status == 1)
    return db.scalar(stmt.with_for_update())


def _eligible_teachers():
    stmt = (
        select(accounts.c.id, accounts.c.real_name)
        .join(roles, roles.c.id == accounts.c.role_id)
        .where(accounts.c.user_type == "employee", accounts.c.status == "normal",
               roles.c.status == 1, roles.c.role_code != "admin")
    )
    for permission in ("leaves:read", "leaves:approve", "tickets:read", "tickets:write"):
        grant = role_permissions.alias()
        stmt = stmt.join(grant, (grant.c.role_id == roles.c.id) & (grant.c.permission == permission))
    return stmt


def teacher_options(db: Session, keyword: str, limit: int):
    stmt = _eligible_teachers()
    if keyword:
        stmt = stmt.where(accounts.c.real_name.contains(keyword, autoescape=True))
    return db.execute(stmt.order_by(accounts.c.id).limit(limit)).mappings().all()


def lock_eligible_teacher(db: Session, employee_id: int) -> bool:
    return db.scalar(_eligible_teachers().where(accounts.c.id == employee_id).with_for_update()) is not None


def create_student_profile(db: Session, student_id: int, teacher_id: int, country: str) -> None:
    db.execute(insert(student_info).values(
        user_id=student_id, class_teacher_id=teacher_id, abroad_country=country,
    ))


def student_destination(db: Session, student_id: int) -> str | None:
    return db.scalar(select(student_info.c.abroad_country).where(student_info.c.user_id == student_id))
