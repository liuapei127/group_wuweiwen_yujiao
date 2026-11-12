from sqlalchemy import select, insert, or_
from .models import onboarding_guide as guide

class OnboardingRepository:
    def __init__(self, db):
        self.db = db

    def search(self, keyword, category, page, page_size):
        stmt = select(guide.c.id, guide.c.title, guide.c.category, guide.c.content, guide.c.update_time).where(guide.c.status == 1)
        if category:
            stmt = stmt.where(guide.c.category == category)
        if keyword:
            stmt = stmt.where(or_(guide.c.title.contains(keyword, autoescape=True), guide.c.content.contains(keyword, autoescape=True)))
        return [dict(row._mapping) for row in self.db.execute(stmt.order_by(guide.c.sort_order, guide.c.id).offset((page - 1) * page_size).limit(page_size))]

    def create(self, values):
        return self.db.execute(insert(guide).values(**values)).inserted_primary_key[0]
