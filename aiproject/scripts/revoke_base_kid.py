"""Revoke sessions associated with a signing key already disabled in the BASE keyset."""
import argparse

from app.core.database import SessionLocal
from app.core.security import base_session
from app.core.security.base_jwt import BaseKeyConfigError, load_keyset
from app.modules.auth import service_identity


def revoke_disabled_kid(db, kid: str) -> int:
    keyset = load_keyset()
    if not any(key.kid == kid and key.status == "disabled" for key in keyset.keys):
        raise BaseKeyConfigError("请先在 BASE 密钥配置中停用该 kid")
    base_session.revoke_sessions_for_kid(db, kid)
    return service_identity.revoke_sessions_for_kid(db, kid)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("kid")
    args = parser.parse_args()
    with SessionLocal() as db:
        service_count = revoke_disabled_kid(db, args.kid)
    print(f"已撤销受影响的员工会话和刷新家族，以及 {service_count} 个服务会话")


if __name__ == "__main__":
    main()
