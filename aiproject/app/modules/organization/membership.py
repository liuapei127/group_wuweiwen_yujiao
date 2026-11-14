"""Live primary-organization membership with MySQL audit triggers."""
from sqlalchemy import BigInteger, DateTime, String, and_, column, delete, insert, or_, select, table, text, update

from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.security.credentials import utc_now
from app.modules.auth.models import accounts, roles
from app.modules.auth.repository import AuthRepository

from .models import sys_organization

members = table("sys_org_member", column("id", BigInteger), column("user_id", BigInteger),
                column("org_id", BigInteger), column("status", String),
                column("effective_from", DateTime), column("effective_to", DateTime))
primary = table("sys_user_primary_org", column("user_id", BigInteger), column("member_id", BigInteger))
history = table("sys_org_member_history", column("member_id", BigInteger), column("user_id", BigInteger),
                column("org_id", BigInteger), column("status_before", String), column("status_after", String),
                column("effective_from_before", DateTime), column("effective_from_after", DateTime),
                column("effective_to_before", DateTime), column("effective_to_after", DateTime),
                column("change_type", String), column("primary_pointer_cleared", BigInteger),
                column("actor_type", String), column("actor_user_id", BigInteger), column("changed_at", DateTime))


def _active(now):
    return and_(members.c.status == "active", members.c.effective_from <= now,
                or_(members.c.effective_to.is_(None), members.c.effective_to > now))


def _employee():
    return and_(accounts.c.status == "normal", accounts.c.user_type.in_(("employee", "admin")))


def effective_primary(db, user_id: int):
    return db.scalar(select(members.c.org_id).select_from(
        primary.join(members, primary.c.member_id == members.c.id)
        .join(accounts, accounts.c.id == members.c.user_id)
        .join(sys_organization, sys_organization.c.id == members.c.org_id)
    ).where(primary.c.user_id == user_id, _active(utc_now()), _employee(), sys_organization.c.status == 1))


def _manager_organizations(manager_id: int):
    roots = select(sys_organization.c.id).where(
        sys_organization.c.manager_id == manager_id, sys_organization.c.status == 1,
        select(accounts.c.id).where(accounts.c.id == manager_id, _employee()).exists(),
    ).cte("managed_organizations", recursive=True)
    return roots.union(select(sys_organization.c.id).join(
        roots, sys_organization.c.parent_id == roots.c.id,
    ).where(sys_organization.c.status == 1))


def managed_employees_query(manager_id: int):
    tree = _manager_organizations(manager_id)
    return select(members.c.user_id).distinct().join(accounts, accounts.c.id == members.c.user_id).where(
        _active(utc_now()), _employee(), members.c.org_id.in_(select(tree.c.id)),
    )


def list_memberships(db, user_id: int):
    query = select(members, sys_organization.c.org_name).join(
        sys_organization, sys_organization.c.id == members.c.org_id,
    ).where(members.c.user_id == user_id).order_by(members.c.org_id)
    actual_primary = effective_primary(db, user_id)
    return [dict(row, primary=row["org_id"] == actual_primary) for row in db.execute(query).mappings()]


def _audit_pointer(db, member, actor_id, now):
    db.execute(insert(history).values(
        member_id=member["id"], user_id=member["user_id"], org_id=member["org_id"],
        status_before=member["status"], status_after=member["status"],
        effective_from_before=member["effective_from"], effective_from_after=member["effective_from"],
        effective_to_before=member["effective_to"], effective_to_after=member["effective_to"],
        change_type="pointer_cleared", primary_pointer_cleared=1,
        actor_type="system" if actor_id is None else "user", actor_user_id=actor_id, changed_at=now,
    ))


def _replace_primary(db, user_id, member_id, actor_id, now):
    old_id = db.scalar(select(primary.c.member_id).where(primary.c.user_id == user_id).with_for_update())
    if old_id == member_id:
        return
    if old_id is not None:
        old = db.execute(select(members).where(members.c.id == old_id)).mappings().one()
        db.execute(delete(primary).where(primary.c.user_id == user_id))
        _audit_pointer(db, old, actor_id, now)
    if member_id is not None:
        db.execute(insert(primary).values(user_id=user_id, member_id=member_id))


def save_membership(db, user_id, org_id, payload, actor_id):
    try:
        now = utc_now()
        if db.scalar(select(accounts.c.id).where(accounts.c.id == user_id, _employee()).with_for_update()) is None:
            raise BusinessError(404, "员工不可用")
        if db.scalar(select(sys_organization.c.id).where(
            sys_organization.c.id == org_id, sys_organization.c.status == 1,
        )) is None:
            raise BusinessError(404, "组织不存在或已停用")
        if payload.effective_to is not None and payload.effective_to <= payload.effective_from:
            raise BusinessError(422, "有效期结束时间必须晚于开始时间")
        if payload.primary and (payload.status != "active" or payload.effective_from > now
                                or (payload.effective_to is not None and payload.effective_to <= now)):
            raise BusinessError(422, "主部门必须是当前有效的成员关系")

        db.execute(text("SET @base_org_actor_user_id = :id, @base_org_reason = NULL"), {"id": actor_id})
        pair = (members.c.user_id == user_id, members.c.org_id == org_id)
        member_id = db.scalar(select(members.c.id).where(*pair).with_for_update())
        values = dict(status=payload.status, effective_from=payload.effective_from, effective_to=payload.effective_to)
        if member_id is None:
            db.execute(insert(members).values(user_id=user_id, org_id=org_id, **values))
            member_id = db.scalar(select(members.c.id).where(*pair))
        else:
            db.execute(update(members).where(*pair).values(**values))
        if payload.primary:
            _replace_primary(db, user_id, member_id, actor_id, now)
        elif db.scalar(select(primary.c.member_id).where(primary.c.user_id == user_id)) == member_id:
            _replace_primary(db, user_id, None, actor_id, now)
        db.execute(text("SET @base_org_actor_user_id = NULL, @base_org_reason = NULL"))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"id": member_id}


def clear_expired_primary(db) -> int:
    now = utc_now()
    expired = select(primary.c.user_id).join(members, members.c.id == primary.c.member_id).where(
        ~_active(now),
    ).order_by(primary.c.user_id).limit(200)
    try:
        users = list(db.scalars(expired))
        db.rollback()
        count = 0
        for user_id in users:
            db.scalar(select(accounts.c.id).where(accounts.c.id == user_id).with_for_update())
            record = db.execute(select(primary.c.member_id).join(members, members.c.id == primary.c.member_id).where(
                primary.c.user_id == user_id, ~_active(now),
            ).with_for_update()).first()
            if record:
                _replace_primary(db, user_id, None, None, now)
                count += 1
        db.commit()
        return count
    except Exception:
        db.rollback()
        raise


def _eligible_managers():
    return select(accounts.c.id, accounts.c.real_name).join(roles, accounts.c.role_id == roles.c.id).where(
        accounts.c.user_type == "employee", accounts.c.status == "normal",
        roles.c.role_code == "manager", roles.c.status == 1,
    )


def manager_options(db: Session) -> list[dict]:
    rows = db.execute(_eligible_managers().order_by(accounts.c.real_name, accounts.c.id)).mappings()
    return [dict(row) for row in rows]


def assign_manager(db: Session, org_id: int, manager_id: int | None, actor_id: int) -> dict:
    try:
        if manager_id is not None:
            manager = db.execute(_eligible_managers().where(accounts.c.id == manager_id).with_for_update()).first()
            if manager is None:
                raise BusinessError(422, "请选择启用的主管账号")
        organization = db.execute(select(sys_organization.c.manager_id).where(
            sys_organization.c.id == org_id, sys_organization.c.status == 1,
        ).with_for_update()).first()
        if organization is None:
            raise BusinessError(404, "组织不存在或已停用")
        if organization.manager_id != manager_id:
            db.execute(update(sys_organization).where(sys_organization.c.id == org_id).values(
                manager_id=manager_id, update_time=utc_now(),
            ))
            AuthRepository(db).audit(actor_id, "organization_manager_update", org_id, {
                "previous_manager_id": organization.manager_id, "manager_id": manager_id,
            })
        db.commit()
    except Exception:
        db.rollback()
        raise
    return {"id": org_id, "manager_id": manager_id}
