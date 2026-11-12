"""Select changed sources in bounded batches and insert uniquely keyed notifications."""
import hashlib
from contextlib import contextmanager
from sqlalchemy import select, insert, and_, or_, case, text
from sqlalchemy.exc import IntegrityError
from app.shared.utils.time_util import now_naive
from .models import todo_item as todos, notification_log as notices
from .sync_repository import SOURCES
from .synchronization import synchronize_source


@contextmanager
def scanner_lock(db):
    bind = db.get_bind()
    if bind.dialect.name != "mysql":
        yield True
        return
    engine = getattr(bind, "engine", bind)
    # Use a dedicated connection: db.commit() may return its own connection to a pool.
    with engine.connect() as control:
        database = control.execute(text("SELECT DATABASE()")).scalar_one()
        name = "ent.scan." + hashlib.sha256(database.encode()).hexdigest()[:40]
        acquired = control.execute(text("SELECT GET_LOCK(:name, 0)"), {"name": name}).scalar_one() == 1
        try:
            yield acquired
        finally:
            if acquired:
                control.execute(text("SELECT RELEASE_LOCK(:name)"), {"name": name})


def _lock(stmt, db):
    return stmt.with_for_update(skip_locked=db.get_bind().dialect.name == "mysql")


def collect_reminders(db, *, employee_ids=None):
    created = delivered = 0
    for related, (table, owner_column, kind, title) in SOURCES.items():
        owner = table.c[owner_column]
        valid = table.c.service_type == "leave" if related == "student_admin_service" else True
        active = and_(valid, owner.is_not(None), table.c.status.in_(["pending", "processing"]))
        marker = case((table.c.service_type != "leave", "missing"), (owner.is_(None), "unassigned"), else_=table.c.status) if related == "student_admin_service" else case((owner.is_(None), "unassigned"), else_=table.c.status)
        joined = table.outerjoin(todos, and_(todos.c.related_type == related, todos.c.related_id == table.c.id))
        changed = or_(todos.c.source_status.is_(None), todos.c.source_status != marker,
                      and_(active, todos.c.assignee_id != owner),
                      and_(~active, todos.c.status.in_(["pending", "in_progress"])))
        stmt = select(table.c.id).select_from(joined).where(or_(and_(todos.c.id.is_(None), active), and_(todos.c.id.is_not(None), changed)))
        if employee_ids is not None:
            # Include the former owner so reassignment/unassignment is reconciled too.
            stmt = stmt.where(or_(owner.in_(employee_ids), todos.c.assignee_id.in_(employee_ids)))
        candidate_ids = db.execute(stmt.order_by(table.c.id).limit(200)).scalars().all()
        if candidate_ids:
            # Do not lock the outer join or its nonexistent todo/index gaps.
            # Lock concrete source PKs first; synchronization follows source -> todo.
            locked = select(table.c.id).where(table.c.id.in_(candidate_ids)).order_by(table.c.id)
            for source_id in db.execute(_lock(locked, db)).scalars().all():
                created += int(synchronize_source(db, related, source_id))
        missing = select(todos.c.related_id).where(todos.c.related_type == related, todos.c.status.in_(["pending", "in_progress"]), ~select(table.c.id).where(table.c.id == todos.c.related_id).exists())
        if employee_ids is not None:
            missing = missing.where(todos.c.assignee_id.in_(employee_ids))
        for source_id in db.execute(missing.order_by(todos.c.id).limit(200)).scalars().all():
            synchronize_source(db, related, source_id)
    # Synchronization may create a due_time in the next second. Capture the cutoff
    # after all source updates so this batch can notify its new assignments.
    now = now_naive()
    # Lock each due todo, then use a current read and a unique key as final protection.
    stmt = select(todos).where(todos.c.status.in_(["pending", "in_progress"]), todos.c.due_time <= now)
    if employee_ids is not None:
        stmt = stmt.where(todos.c.assignee_id.in_(employee_ids))
    # Exclude already-delivered revisions so later batches cannot starve.
    from sqlalchemy import cast, String, literal
    if db.get_bind().dialect.name == "mysql":
        from sqlalchemy import func
        key_expr = func.concat("todo:", todos.c.id, ":", todos.c.assignee_id, ":", todos.c.assignment_version)
    else:
        key_expr = literal("todo:") + cast(todos.c.id, String) + ":" + cast(todos.c.assignee_id, String) + ":" + cast(todos.c.assignment_version, String)
    stmt = stmt.where(~select(notices.c.id).where(notices.c.dedup_key == key_expr).exists())
    for row in db.execute(_lock(stmt.order_by(todos.c.id).limit(200), db)).mappings().all():
        key = f"todo:{row['id']}:{row['assignee_id']}:{row['assignment_version']}"
        if db.execute(select(notices.c.id).where(notices.c.dedup_key == key).with_for_update()).first():
            continue
        try:
            if db.get_bind().dialect.name == "mysql":
                db.execute(insert(notices).values(user_id=row["assignee_id"], notification_type="todo_due", related_type="todo_item", related_id=row["id"], title=row["title"], content=row["description"] or row["title"], channel="system", status="sent", dedup_key=key, create_time=now))
            else:
                with db.begin_nested():
                    db.execute(insert(notices).values(user_id=row["assignee_id"], notification_type="todo_due", related_type="todo_item", related_id=row["id"], title=row["title"], content=row["description"] or row["title"], channel="system", status="sent", dedup_key=key, create_time=now))
            delivered += 1
        except IntegrityError:
            if db.get_bind().dialect.name == "mysql":
                raise
            if not db.execute(select(notices.c.id).where(notices.c.dedup_key == key).with_for_update()).first():
                raise
    return {"todos_created": created, "system_notifications_created": delivered}
