from app.shared.utils.serialization import json_snapshot
from sqlalchemy.exc import IntegrityError
from app.core.exceptions import BusinessError
from app.core.security.authorization import require_student_scope
from app.shared.utils.time_util import now_naive
from .identity import default_exam_key, submission_hash
from .repository import ScoreRepository


def _require_active_student(repo, student_id):
    user = repo.get_student(student_id)
    if not user or user.user_type != "student" or user.status != "normal":
        raise BusinessError(422, "学生不存在或已停用")


def _replay(row, fingerprint, submission_key=None):
    if submission_key and row["submission_key"] != submission_key:
        raise BusinessError(409, "该考试已由另一提交创建，请查询现有成绩")
    if row["submission_hash"] != fingerprint:
        raise BusinessError(409, "该考试或提交标识已存在且内容不同，请使用成绩更正接口")
    return {"id": row["id"], "version": row["version"], "replayed": True}


def create_score(body, db, p):
    require_student_scope(p, body.student_id, "scores:write")
    repo = ScoreRepository(db)
    _require_active_student(repo, body.student_id)
    values = body.model_dump(exclude={"submission_key"})
    values["exam_key"] = values.get("exam_key") or default_exam_key(body.course_name, body.semester)
    fingerprint = submission_hash(values)
    key = getattr(body, "submission_key", None)
    try:
        if key:
            existing = repo.by_key(body.student_id, "submission_key", key)
            if existing:
                return _replay(existing, fingerprint, key)
        existing = repo.by_key(body.student_id, "exam_key", values["exam_key"])
        if existing:
            return _replay(existing, fingerprint, key)
        now = now_naive()
        rid = repo.create(dict(**values, submission_key=key, submission_hash=fingerprint, version=1, recorded_by=p.employee_id, create_time=now, update_time=now))
        row = repo.get(rid)
        repo.add_history(dict(score_id=rid, version=1, operation="create", changed_by=p.employee_id, change_reason=None, before_data=None, after_data=json_snapshot(row), create_time=now))
        db.commit()
        return {"id": rid, "version": 1, "replayed": False}
    except IntegrityError:
        db.rollback()
        # Current locking reads see the winner even under MySQL REPEATABLE READ.
        existing = repo.by_key(body.student_id, "submission_key", key, lock=True) if key else None
        existing = existing or repo.by_key(body.student_id, "exam_key", values["exam_key"], lock=True)
        if existing:
            return _replay(existing, fingerprint, key)
        raise
    except Exception:
        db.rollback()
        raise


def list_scores(student_id, semester, limit, db, p):
    require_student_scope(p, student_id, "scores:read")
    return ScoreRepository(db).list_scores(student_id, semester, limit)


def correct_score(score_id, body, db, p):
    repo = ScoreRepository(db)
    try:
        row = repo.get(score_id, lock=True)
        if row is None:
            raise BusinessError(404, "成绩不存在")
        require_student_scope(p, row["student_id"], "scores:write")
        if body.student_id != row["student_id"]:
            raise BusinessError(422, "不得更换成绩所属学生")
        _require_active_student(repo, body.student_id)
        expected = getattr(body, "expected_version", None)
        if expected is not None and expected != row["version"]:
            raise BusinessError(409, "成绩版本已变化，请刷新后重试")
        values = body.model_dump(exclude={"expected_version", "correction_reason"})
        if all(row[k] == v for k, v in values.items()):
            return {"id": score_id, "version": row["version"], "unchanged": True}
        now = now_naive()
        values.update(version=row["version"] + 1, recorded_by=p.employee_id, update_time=now)
        repo.update(score_id, values)
        repo.add_history(dict(score_id=score_id, version=values["version"], operation="correct", changed_by=p.employee_id, change_reason=getattr(body, "correction_reason", None), before_data=json_snapshot(row), after_data=json_snapshot(repo.get(score_id)), create_time=now))
        db.commit()
        return {"id": score_id, "version": values["version"]}
    except Exception:
        db.rollback()
        raise


def score_history(score_id, limit, db, p):
    repo = ScoreRepository(db)
    row = repo.get(score_id)
    if row is None:
        raise BusinessError(404, "成绩不存在")
    require_student_scope(p, row["student_id"], "scores:read")
    return repo.history(score_id, limit)
