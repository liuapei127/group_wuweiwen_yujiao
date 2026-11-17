"""Create customer records for visitors claimed before customer creation became automatic."""

from sqlalchemy import select

from app.core.database import SessionLocal
from app.modules.consultant.intake_service import backfill_claimed_customer
from app.modules.consultant.models import VisitorIntake


def main() -> None:
    after = 0
    created = 0
    while True:
        with SessionLocal() as db:
            visitor_ids = list(db.scalars(select(VisitorIntake.visitor_id).where(
                VisitorIntake.visitor_id > after, VisitorIntake.crm_lead_id.is_(None),
            ).order_by(VisitorIntake.visitor_id).limit(100)))
        if not visitor_ids:
            break
        for visitor_id in visitor_ids:
            with SessionLocal.begin() as db:
                inserted = backfill_claimed_customer(db, visitor_id)
            created += inserted
        after = visitor_ids[-1]
    print(f"Customer records created: {created}")


if __name__ == "__main__":
    main()
