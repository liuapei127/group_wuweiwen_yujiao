from app.core.security.authorization import require_permission
from app.shared.utils.time_util import now_naive
from .repository import OnboardingRepository


def guides(keyword, category, page, page_size, db, p):
    return OnboardingRepository(db).search(keyword, category, page, page_size)


def create_guide(body, db, p):
    require_permission(p, "guides:write")
    now = now_naive()
    rid = OnboardingRepository(db).create(dict(**body.model_dump(), sort_order=0, status=1, create_time=now, update_time=now))
    db.commit()
    return {"id": rid}
