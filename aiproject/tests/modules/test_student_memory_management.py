"""User-controlled memory and versioned optional proof, using isolated stores."""
from datetime import datetime
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, select, func, text
from sqlalchemy.orm import Session
from app.core.exceptions import BusinessError
from app.modules.student.models import StuMem0Memory
from app.modules.student import assistant_mem0 as memory, memory_service
from tests.modules.test_student_workspace import db, cid, leave
from app.modules.student import assistant_tasks as tasks
from app.modules.student_admin.models import LeaveAttachment


@pytest.fixture
def memory_db():
    engine = create_engine("sqlite://")
    StuMem0Memory.__table__.create(engine)
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE sys_user(id INTEGER PRIMARY KEY,user_type TEXT,status TEXT)"))
        conn.execute(text("INSERT INTO sys_user VALUES(2,'student','normal'),(3,'student','normal')"))
    with Session(engine) as session:
        yield session
    engine.dispose()


def remember(db, sid, text, assistant="好的，我记下了。"):
    memory.search_memories(db, student_id=sid, query=text)
    memory.remember_turn(db, student_id=sid, user_text=text, assistant_text=assistant, conversation_id="review")


def test_memory_owner_edit_stale_delete_and_clear(memory_db):
    remember(memory_db, 2, "我喜欢简短的回答")
    remember(memory_db, 3, "我喜欢详细的回答")
    page = memory_service.listing(memory_db, 2)
    assert len(page["items"]) == 1 and page["storage"] == "local"
    row = page["items"][0]
    with pytest.raises(BusinessError) as forbidden:
        memory_service.correct(memory_db, 3, row["id"], "不同账号", row["version"])
    assert forbidden.value.status_code == 404
    changed = memory_service.correct(memory_db, 2, row["id"], "我喜欢有步骤的回答", row["version"])
    assert changed["version"] != row["version"]
    with pytest.raises(BusinessError) as stale:
        memory_service.erase(memory_db, 2, row["id"], row["version"])
    assert stale.value.status_code == 409
    assert memory_service.erase(memory_db, 2, row["id"], changed["version"])["deleted"]
    assert memory.search_memories(memory_db, student_id=2, query="我喜欢怎样回答") == []
    assert len(memory_service.listing(memory_db, 3)["items"]) == 1
    assert memory_service.clear(memory_db, 2)["deleted_count"] == 0
    assert len(memory_service.listing(memory_db, 3)["items"]) == 1


def test_name_correction_replaces_stale_names_and_never_reads_assistant_claims(memory_db):
    remember(memory_db, 2, "我叫小明")
    remember(memory_db, 2, "叫我小王")
    page = memory_service.listing(memory_db, 2)
    assert len(page["items"]) == 1
    row = page["items"][0]
    changed = memory_service.correct(memory_db, 2, row["id"], "小李", row["version"])
    assert changed["memory"] == "学生姓名：小李"
    assert memory.search_memories(memory_db, student_id=2, query="我叫什么") == ["学生姓名：小李"]
    remember(memory_db, 2, "我要去医院", "你刚到德国，已经替你联系学校。")
    assert len(memory_service.listing(memory_db, 2)["items"]) == 1
    remember(memory_db, 2, "我喜欢详细一点", "你已经入学。")
    assert "已经入学" not in " ".join(memory.search_memories(memory_db, student_id=2, query="回答方式"))
    remember(memory_db, 2, "我喜欢详细一点")
    assert len(memory_service.listing(memory_db, 2)["items"]) == 2


def test_legacy_recall_removes_old_assistant_summaries_without_rewriting_history(memory_db):
    now = datetime(2026, 11, 17)
    row = StuMem0Memory(user_id="stu_2", memory="学生说：我想家；助手：你刚到德国", create_time=now, update_time=now)
    memory_db.add(row)
    memory_db.commit()
    assert memory.search_memories(memory_db, student_id=2, query="想家") == ["学生说：我想家"]
    assert memory_service.listing(memory_db, 2)["items"][0]["memory"].endswith("你刚到德国")


def test_memory_pagination_and_local_only_guard(memory_db, monkeypatch):
    from pydantic import SecretStr
    from app.core.config import get_settings
    for n in range(4):
        remember(memory_db, 2, "请记住偏好" + str(n))
    first = memory_service.listing(memory_db, 2, limit=2)
    second = memory_service.listing(memory_db, 2, first["items"][-1]["id"], limit=2)
    assert first["has_more"] and not second["has_more"]
    assert {r["id"] for r in first["items"]}.isdisjoint(r["id"] for r in second["items"])
    monkeypatch.setattr(get_settings(), "mem0_api_key", SecretStr("external"))
    with pytest.raises(BusinessError) as conflict:
        memory_service.clear(memory_db, 2)
    assert conflict.value.status_code == 409


def test_optional_proof_is_owned_persistent_and_invalidates_confirmation(db):
    LeaveAttachment.__table__.create(db.bind)
    now = datetime(2026, 11, 17)
    proof, other = str(uuid4()), str(uuid4())
    db.add_all([LeaveAttachment(id=value, student_id=sid, filename="证明.pdf",
                  content_type="application/pdf", content=b"%PDF-1.4", created_at=now)
                for value, sid in ((proof, 2), (other, 3))])
    db.commit()
    draft = tasks.save_draft(db, 2, cid(db), "leave", leave(), None)
    with pytest.raises(BusinessError):
        tasks.change_attachment(db, 3, draft["id"], draft["version"], proof)
    with pytest.raises(BusinessError):
        tasks.change_attachment(db, 2, draft["id"], draft["version"], other)
    changed = tasks.change_attachment(db, 2, draft["id"], draft["version"], proof)
    assert changed["version"] == draft["version"] + 1 and changed["attachment"]["filename"] == "证明.pdf"
    assert tasks.repo.task(db, 2, draft["id"]).payload["attachment_id"] == proof
    with pytest.raises(BusinessError) as stale:
        tasks.decide(db, 2, draft["id"], draft["version"])
    assert stale.value.status_code == 409
    removed = tasks.change_attachment(db, 2, draft["id"], changed["version"], None)
    assert removed["attachment"] is None and removed["status"] == "awaiting_confirmation"
    assert db.scalar(select(func.count()).select_from(LeaveAttachment)) == 2


def test_clear_blocks_old_inflight_memory_and_hides_control_records(memory_db):
    from app.modules.student import memory_repository as repository
    remember(memory_db, 2, "我喜欢简短回答")
    memory.search_memories(memory_db, student_id=2, query="叫我旧名字")
    memory_service.clear(memory_db, 2)
    memory.remember_turn(memory_db, student_id=2, user_text="叫我旧名字", assistant_text="好", conversation_id="inflight")
    assert memory_service.listing(memory_db, 2)["items"] == []
    assert memory.search_memories(memory_db, student_id=2, query="我叫什么") == []
    control = memory_db.scalar(select(StuMem0Memory).where(StuMem0Memory.memory == repository.STATE_MEMORY))
    with pytest.raises(BusinessError) as unavailable:
        memory_service.erase(memory_db, 2, control.id, memory_service.version(control))
    assert unavailable.value.status_code == 404
    remember(memory_db, 2, "叫我新名字")
    assert memory_service.listing(memory_db, 2)["items"][0]["memory"] == "学生姓名：新名字"
    assert len(memory_service.listing(memory_db, 2)["items"]) == 1


def test_reserved_control_content_cannot_be_created_by_user(memory_db):
    from app.modules.student.memory_repository import STATE_MEMORY
    remember(memory_db, 2, "我喜欢简短回答")
    row = memory_service.listing(memory_db, 2)["items"][0]
    for content in (STATE_MEMORY, "  " + STATE_MEMORY + "  "):
        with pytest.raises(BusinessError) as invalid:
            memory_service.correct(memory_db, 2, row["id"], content, row["version"])
        assert invalid.value.status_code == 422
    assert memory_service.listing(memory_db, 2)["items"][0]["memory"] == row["memory"]
