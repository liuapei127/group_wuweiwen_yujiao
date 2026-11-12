"""Read-only BASE identity mapping. It does not log in or issue tokens."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security.base_jwt import USER_TYPES
from app.core.security.rbac import PERMISSIONS
from app.modules.auth.models import accounts, role_permissions, roles

# Columns actually sent to the database. password_hash is intentionally absent.
IDENTITY_ACCOUNT_COLUMNS = (
    accounts.c.id,
    accounts.c.username,
    accounts.c.user_type,
    accounts.c.status,
    accounts.c.role_id,
    roles.c.role_code,
    roles.c.role_name,
    roles.c.status.label("role_status"),
)
_PORTAL_LOGIN_TYPES = frozenset({"employee", "admin"})


class BaseIdentityError(Exception):
    """The account cannot be resolved. The message stays generic."""

    def __init__(self, code: str):
        if code not in {"missing", "disabled", "invalid_user_type", "missing_role", "disabled_role"}:
            raise ValueError("unknown identity error")
        self.code = code
        super().__init__("BASE 身份不可用")


@dataclass(frozen=True)
class BaseIdentity:
    user_id: int
    sub: str
    username: str
    user_type: str
    role_id: int
    role_code: str
    role_name: str
    permissions: frozenset[str]

    @property
    def ent_login_allowed(self) -> bool:
        """Existing ENT login accepts only these account classes. This does not issue a token."""
        return self.user_type in _PORTAL_LOGIN_TYPES


def resolve_identity(db: Session, user_id: int) -> BaseIdentity:
    if isinstance(user_id, bool) or not isinstance(user_id, int) or user_id < 1:
        raise BaseIdentityError("missing")
    row = db.execute(_account_select(user_id)).mappings().first()
    if row is None:
        raise BaseIdentityError("missing")
    user_type = row["user_type"]
    if user_type not in USER_TYPES:
        raise BaseIdentityError("invalid_user_type")
    if row["status"] != "normal":
        raise BaseIdentityError("disabled")
    role_id = row["role_id"]
    if role_id is None or row["role_code"] is None or row["role_name"] is None:
        raise BaseIdentityError("missing_role")
    if row["role_status"] != 1:
        raise BaseIdentityError("disabled_role")
    username = row["username"]
    if not isinstance(username, str) or username.strip() == "":
        raise BaseIdentityError("missing")
    stored = set(db.execute(
        select(role_permissions.c.permission).where(role_permissions.c.role_id == role_id)
    ).scalars())
    return BaseIdentity(
        user_id=user_id,
        sub=str(user_id),
        username=username,
        user_type=user_type,
        role_id=int(role_id),
        role_code=row["role_code"],
        role_name=row["role_name"],
        permissions=frozenset(stored & set(PERMISSIONS)),
    )


def _account_select(user_id: int):
    return select(*IDENTITY_ACCOUNT_COLUMNS).select_from(
        accounts.outerjoin(roles, accounts.c.role_id == roles.c.id)
    ).where(accounts.c.id == user_id)
