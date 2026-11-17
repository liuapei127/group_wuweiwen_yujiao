"""Student-controlled local memories: self-reports, never academic authority."""
import hashlib
import json
import re
from datetime import datetime
from secrets import token_hex
from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.shared.utils.time_util import now_naive
from . import assistant_mem0 as memory
from . import memory_repository as repository


def _local_only():
    if get_settings().mem0_api_key.get_secret_value().strip():
        raise BusinessError(409, "当前已配置外部记忆服务，请先统一外部记忆的管理方式")


def metadata(row):
    try:
        value = json.loads(row.metadata_json or "{}")
        return value if isinstance(value, dict) else {}
    except (TypeError, ValueError):
        return {}


def version(row):
    raw = json.dumps([row.id, row.memory, row.metadata_json or ""], ensure_ascii=False)
    return hashlib.sha256(raw.encode()).hexdigest()


def item(row):
    meta = metadata(row)
    kind = meta.get("kind") or ("name" if row.memory.startswith("学生姓名：") else "legacy")
    return {"id": row.id, "memory": row.memory, "kind": kind,
            "version": version(row), "create_time": row.create_time, "update_time": row.update_time}


def listing(db, student_id, before_id=None, limit=20):
    _local_only()
    rows = repository.rows(db, memory.user_key(student_id), before_id=before_id, limit=limit + 1)
    return {"items": [item(row) for row in rows[:limit]], "has_more": len(rows) > limit, "storage": "local",
            "notes": "这些是交流中的自述和偏好，不会修改学籍或授权办理。删除长期记忆不删除聊天历史；已有对话仍可能包含原文，新对话不会再把已删除内容作为长期记忆召回。"}


def _owned_version(db, student_id, memory_id, expected):
    row = repository.owned(db, memory.user_key(student_id), memory_id, lock=True)
    if row is None:
        raise BusinessError(404, "记忆不存在")
    if version(row) != expected:
        db.rollback()
        raise BusinessError(409, "这条记忆已更新，请刷新后再核对")
    return row


def correct(db, student_id, memory_id, text, expected_version):
    _local_only()
    text = text.strip()
    if not text:
        raise BusinessError(422, "记忆内容不能为空")
    if text.startswith("__student_assistant_"):
        raise BusinessError(422, "记忆内容不能使用内部保留标记")
    if memory._sensitive(text):
        raise BusinessError(422, "这类敏感内容不保存为长期记忆")
    try:
        if repository.lock_owner(db, student_id) is None:
            raise BusinessError(403, "学生账号不可用")
        row = _owned_version(db, student_id, memory_id, expected_version)
        fact = memory._name_fact_from_user(text)
        if row.memory.startswith("学生姓名：") and not fact and re.fullmatch(r"[A-Za-z\u4e00-\u9fff·]{2,20}", text.strip()):
            fact = "学生姓名：" + text.strip()
        row.memory = fact or text.strip()
        if row.memory.startswith("学生姓名："):
            for sibling in repository.name_rows(db, row.user_id):
                if sibling.id != row.id:
                    db.delete(sibling)
        meta = metadata(row)
        meta.update(kind=memory.memory_kind(row.memory), source="student_correction",
                    user_edited=True, revision=token_hex(16), schema_version=2,
                    confirmed_at=datetime.now().isoformat(timespec="microseconds"))
        row.metadata_json = json.dumps(meta, ensure_ascii=False)
        row.update_time = now_naive()
        repository.advance_generation(db, memory.user_key(student_id), row.update_time)
        db.commit()
        db.refresh(row)
        return item(row)
    except Exception:
        db.rollback()
        raise


def erase(db, student_id, memory_id, expected_version):
    _local_only()
    try:
        if repository.lock_owner(db, student_id) is None:
            raise BusinessError(403, "学生账号不可用")
        row = _owned_version(db, student_id, memory_id, expected_version)
        db.delete(row)
        repository.advance_generation(db, memory.user_key(student_id), now_naive())
        db.commit()
        return {"deleted": True}
    except Exception:
        db.rollback()
        raise


def clear(db, student_id):
    _local_only()
    try:
        if repository.lock_owner(db, student_id) is None:
            raise BusinessError(403, "学生账号不可用")
        count = repository.erase_all(db, memory.user_key(student_id))
        repository.advance_generation(db, memory.user_key(student_id), now_naive())
        db.commit()
        return {"deleted_count": count}
    except Exception:
        db.rollback()
        raise
