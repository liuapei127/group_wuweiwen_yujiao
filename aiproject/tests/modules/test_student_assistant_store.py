"""Conversation store on ORM models (SQLite in-memory, no runtime DDL)."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.modules.student import assistant_store
from app.modules.student.models import (
    StuMem0Memory,
    StudentAssistantConversation,
    StudentAssistantMessage,
)


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    for model in (StudentAssistantConversation, StudentAssistantMessage, StuMem0Memory):
        model.__table__.create(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_store_does_not_issue_ddl():
    assert not hasattr(assistant_store, "ensure_schema")
    assert not hasattr(assistant_store, "_CREATE_SQL")


def test_append_and_read_back_turns_in_order(db):
    conversation = assistant_store.create_conversation(db, 1)
    assistant_store.append_turn(
        db,
        student_id=1,
        conversation_id=conversation["id"],
        user_text="我要请假",
        assistant_text="可以请假。先告诉我是病假、事假还是紧急。",
        title_hint="请假咨询",
    )
    assistant_store.append_turn(
        db,
        student_id=1,
        conversation_id=conversation["id"],
        user_text="病假 11月20号到21号",
        assistant_text="好，先按病假。请再补充：事由。",
    )

    turns = assistant_store.recent_turns(db, conversation["id"], limit=4)
    assert [turn["role"] for turn in turns] == ["user", "assistant", "user", "assistant"]
    assert turns[-2]["content"].startswith("病假 11月20号到21号")
    assert turns[0]["content"] == "我要请假"

    latest = assistant_store.recent_turns(db, conversation["id"], limit=1)
    assert latest[0]["content"].startswith("好，先按病假")

    [row] = assistant_store.list_conversations(db, 1)
    assert row["title"] == "请假咨询"


def test_conversation_is_scoped_to_owner(db):
    conversation = assistant_store.create_conversation(db, 1)
    assert assistant_store.get_conversation(db, 2, conversation["id"]) is None
    with pytest.raises(ValueError):
        assistant_store.append_turn(
            db,
            student_id=2,
            conversation_id=conversation["id"],
            user_text="你好",
            assistant_text="你好",
        )
