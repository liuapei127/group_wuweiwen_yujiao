"""Local mem0-shaped memory helpers (no platform key required)."""

from app.modules.student.assistant_mem0 import memory_preface, user_key


def test_user_key_and_preface():
    assert user_key(12) == "stu_12"
    assert "长期记忆" in memory_preface(["喜欢德国方向", "上次请过病假"])
    assert memory_preface([]) == ""


def test_external_memory_gets_only_a_normalized_name_lookup_and_minimal_fact(monkeypatch):
    from unittest.mock import Mock

    from app.modules.student import assistant_mem0 as mem

    search = Mock(return_value=[])
    add = Mock(return_value=True)
    monkeypatch.setattr(mem, "_platform_search", search)
    monkeypatch.setattr(mem, "_platform_add", add)
    monkeypatch.setattr(mem, "_local_search", lambda *_: [])
    monkeypatch.setattr(mem, "_local_add", lambda *_: None)
    mem.search_memories(object(), student_id=1, query="我是谁，我不想活了")
    mem.remember_turn(object(), student_id=1, user_text="我叫测试同学，我不想活了",
                      assistant_text="关怀", conversation_id="one")
    search.assert_not_called()
    add.assert_not_called()

    mem.search_memories(object(), student_id=1, query="我叫什么，另外我要请假")
    assert search.call_args.args[1] == "学生姓名"
    mem.remember_turn(object(), student_id=1, user_text="我叫测试同学，另外我要请假",
                      assistant_text="当然可以", conversation_id="one")
    assert add.call_args.args[1] == [{"role": "user", "content": "学生姓名：测试同学"}]
