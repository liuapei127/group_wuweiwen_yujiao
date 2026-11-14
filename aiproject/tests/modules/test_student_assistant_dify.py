"""STU Dify shell helpers and DSL shape."""

from pathlib import Path

import yaml

from app.modules.student import assistant_dify


ROOT = Path(__file__).resolve().parents[2]
STU_YML = ROOT / "docs" / "dify" / "local-integration" / "stu.yml"
LEGACY_YML = ROOT / "docs" / "dify" / "local-integration" / "stu-legacy-api-stu.yml"


def test_new_stu_dsl_targets_unified_assistant_run():
    doc = yaml.safe_load(STU_YML.read_text(encoding="utf-8"))
    assert doc["app"]["name"] == "留学学生助手 · 统一API"
    nodes = {node["id"]: node for node in doc["workflow"]["graph"]["nodes"]}
    chat = nodes["http_chat"]["data"]
    assert chat["url"].endswith("/api/v1/student/assistant/run")
    assert "stu_api_base" in chat["url"] or "{{#env.stu_api_base#}}" in chat["url"]
    login = nodes["http_login"]["data"]
    assert login["url"].endswith("/api/v1/visitors/login")
    assert "8001" not in chat["url"]
    assert "/api/stu/" not in chat["url"]


def test_legacy_stu_dsl_archived():
    assert LEGACY_YML.is_file()
    text = LEGACY_YML.read_text(encoding="utf-8")
    assert "/api/stu/assistant/chat" in text


def test_ask_dify_requires_key(monkeypatch):
    import asyncio

    import pytest

    from app.core.config import Settings
    from app.core.exceptions import BusinessError

    monkeypatch.setattr(
        assistant_dify,
        "get_settings",
        lambda: Settings(_env_file=None, stu_dify_api_key=""),
    )
    with pytest.raises(BusinessError) as exc:
        asyncio.run(
            assistant_dify.ask_dify(
                query="你好",
                access_token="tok",
                history=[],
                user_key="student_1",
            )
        )
    assert exc.value.status_code == 503
