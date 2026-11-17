"""Account-owned local memory access. No transaction policy or remote writes."""
from sqlalchemy import select, delete, or_
from .models import StuMem0Memory


def rows(db, user_id, *, before_id=None, limit=21, lock=False):
    stmt = select(StuMem0Memory).where(StuMem0Memory.user_id == user_id, StuMem0Memory.memory != STATE_MEMORY)
    if before_id is not None:
        stmt = stmt.where(StuMem0Memory.id < before_id)
    stmt = stmt.order_by(StuMem0Memory.id.desc()).limit(limit)
    return list(db.scalars(stmt.with_for_update() if lock else stmt).all())


def owned(db, user_id, memory_id, *, lock=False):
    stmt = select(StuMem0Memory).where(StuMem0Memory.user_id == user_id, StuMem0Memory.id == memory_id, StuMem0Memory.memory != STATE_MEMORY)
    return db.scalar(stmt.with_for_update().execution_options(populate_existing=True) if lock else stmt)


def erase_all(db, user_id):
    return db.execute(delete(StuMem0Memory).where(StuMem0Memory.user_id == user_id, StuMem0Memory.memory != STATE_MEMORY)).rowcount


def name_rows(db, user_id):
    return list(db.scalars(select(StuMem0Memory).where(StuMem0Memory.user_id == user_id, StuMem0Memory.memory.startswith("学生姓名："))).all())


STATE_MEMORY = "__student_assistant_memory_epoch__"


def lock_owner(db, student_id):
    from app.modules.auth.models import accounts
    return db.scalar(select(accounts.c.id).where(accounts.c.id == student_id,
                     accounts.c.user_type == "student", accounts.c.status == "normal").with_for_update())


def generation(db, user_id, *, current_read=False):
    import json
    stmt = select(StuMem0Memory.metadata_json).where(
        StuMem0Memory.user_id == user_id, StuMem0Memory.memory == STATE_MEMORY).order_by(StuMem0Memory.id.desc()).limit(1)
    value = db.scalar(stmt.with_for_update() if current_read else stmt)
    try:
        return json.loads(value or "{}").get("epoch", "initial")
    except (TypeError, ValueError):
        return "initial"


def advance_generation(db, user_id, now):
    import json
    from secrets import token_hex
    row = db.scalar(select(StuMem0Memory).where(StuMem0Memory.user_id == user_id,
                    StuMem0Memory.memory == STATE_MEMORY).with_for_update().execution_options(populate_existing=True))
    value = json.dumps({"kind": "control", "epoch": token_hex(16)})
    if row is None:
        db.add(StuMem0Memory(user_id=user_id, memory=STATE_MEMORY, metadata_json=value,
                           create_time=now, update_time=now))
    else:
        row.metadata_json = value
        row.update_time = now


def recall_candidates(db, user_id):
    """Bounded account-owned recent facts plus durable name/style anchors.

    Historical question rows must not push a still-valid name/preference outside
    the recall window. Listing is deliberately separate and remains unfiltered.
    """
    base = select(StuMem0Memory).where(StuMem0Memory.user_id == user_id,
                                     StuMem0Memory.memory != STATE_MEMORY)
    ordered = base.order_by(StuMem0Memory.update_time.desc(), StuMem0Memory.id.desc())
    recent = list(db.scalars(ordered.limit(80)).all())
    names = list(db.scalars(ordered.where(StuMem0Memory.memory.startswith("学生姓名：")).limit(2)).all())
    anchors = list(db.scalars(ordered.where(or_(
        StuMem0Memory.memory.startswith("学生姓名："),
        StuMem0Memory.metadata_json.like('%"kind": "preference"%'),
        StuMem0Memory.metadata_json.like('%"kind":"preference"%'),
        StuMem0Memory.memory.startswith("学生自述：我喜欢"),
        StuMem0Memory.memory.startswith("学生自述：我更喜欢"),
        StuMem0Memory.memory.startswith("学生自述：以后请"),
    )).limit(30)).all())
    unique = {row.id: row for row in recent + names + anchors}
    return sorted(unique.values(), key=lambda row: (_confirmation_time(row), row.id), reverse=True)


def _confirmation_time(row):
    """Preserve subsecond choice ordering in JSON even with second-only DB dates."""
    import json
    from datetime import datetime
    try:
        meta = json.loads(row.metadata_json or "{}")
        value = datetime.fromisoformat(meta.get("confirmed_at", ""))
        if value.tzinfo is None:
            return max(row.update_time, value)
    except (TypeError, ValueError, AttributeError):
        pass
    return row.update_time
