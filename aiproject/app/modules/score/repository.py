from sqlalchemy import select, insert, update
from app.modules.student_admin.models import SysUser
from .models import student_score as scores, student_score_history as history

class ScoreRepository:
    def __init__(self, db):
        self.db = db

    def get_student(self, student_id):
        return self.db.get(SysUser, student_id)

    def create(self, values):
        return self.db.execute(insert(scores).values(**values)).inserted_primary_key[0]

    def list_scores(self, student_id, semester, limit):
        stmt = select(scores).where(scores.c.student_id == student_id)
        if semester:
            stmt = stmt.where(scores.c.semester == semester)
        return [dict(row._mapping) for row in self.db.execute(stmt.order_by(scores.c.id.desc()).limit(limit))]

    def get(self, score_id, *, lock=False):
        stmt = select(scores).where(scores.c.id == score_id)
        if lock:
            stmt = stmt.with_for_update()
        row = self.db.execute(stmt).first()
        return dict(row._mapping) if row else None

    def update(self, score_id, values):
        self.db.execute(update(scores).where(scores.c.id == score_id).values(**values))

    def by_key(self, student_id, field, key, *, lock=False):
        stmt = select(scores).where(scores.c.student_id == student_id, scores.c[field] == key)
        if lock:
            stmt = stmt.with_for_update()
        row = self.db.execute(stmt).mappings().first()
        return dict(row) if row else None

    def add_history(self, values):
        self.db.execute(insert(history).values(**values))

    def history(self, score_id, limit):
        return [dict(row) for row in self.db.execute(select(history).where(history.c.score_id == score_id).order_by(history.c.version.desc()).limit(limit)).mappings()]
