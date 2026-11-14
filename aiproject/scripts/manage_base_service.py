"""Manage BASE machine credentials from the server console."""
import argparse
from pathlib import Path

from app.core.database import SessionLocal
from app.modules.auth import service_identity


def main():
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="action", required=True)
    create = commands.add_parser("create")
    create.add_argument("client_id")
    create.add_argument("display_name")
    create.add_argument("audience", nargs="+", choices=sorted(service_identity.RESOURCE_AUDIENCES))
    create.add_argument("--secret-file", required=True, type=Path)
    rotate = commands.add_parser("rotate")
    rotate.add_argument("client_id")
    rotate.add_argument("--grace", type=int, default=0)
    rotate.add_argument("--secret-file", required=True, type=Path)
    disable = commands.add_parser("disable")
    disable.add_argument("client_id")
    args = parser.parse_args()

    with SessionLocal() as db:
        if args.action == "disable":
            service_identity.disable(db, args.client_id)
            return
        import os

        file = os.open(args.secret_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(file, "w", encoding="ascii") as target:
                if args.action == "create":
                    secret = service_identity.create(db, args.client_id, args.display_name, tuple(args.audience))
                else:
                    secret = service_identity.rotate(db, args.client_id, args.grace)
                target.write(secret + "\n")
        except Exception:
            args.secret_file.unlink(missing_ok=True)
            raise


if __name__ == "__main__":
    main()
