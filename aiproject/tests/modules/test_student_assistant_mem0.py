"""Local mem0-shaped memory helpers (no platform key required)."""

from app.modules.student.assistant_mem0 import memory_preface, user_key


def test_user_key_and_preface():
    assert user_key(12) == "stu_12"
    assert "长期记忆" in memory_preface(["喜欢德国方向", "上次请过病假"])
    assert memory_preface([]) == ""
