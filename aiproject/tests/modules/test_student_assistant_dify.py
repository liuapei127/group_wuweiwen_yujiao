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


def test_stu_dsl_has_no_retry_on_write_nodes():
    """重试 /assistant/run 会重复提交请假/投诉；两个写节点都不允许重试。"""
    doc = yaml.safe_load(STU_YML.read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in doc["workflow"]["graph"]["nodes"]}
    for node_id in ("http_login", "http_chat"):
        assert nodes[node_id]["data"]["retry_config"]["retry_enabled"] is False, node_id


def test_stu_dsl_has_llm_fallback_for_generic_replies():
    """后端只会说「我在听」时，画布交给模型回答；有结果的答复原样透传。"""
    doc = yaml.safe_load(STU_YML.read_text(encoding="utf-8"))
    graph = doc["workflow"]["graph"]
    nodes = {node["id"]: node for node in graph["nodes"]}
    llm = nodes["llm_reply"]["data"]
    assert llm["type"] == "llm"
    assert "{{#resolve_auth.history_json#}}" in llm["prompt_template"][0]["text"]
    assert llm["model"]["provider"].startswith("langgenius/")
    guard = nodes["reply_guard"]["data"]
    assert guard["type"] == "if-else"
    assert guard["cases"][0]["conditions"][0]["value"] == "我在听"
    edges = {(edge["source"], edge["sourceHandle"]): edge["target"] for edge in graph["edges"]}
    assert edges[("reply_guard", "true")] == "llm_reply"
    assert edges[("reply_guard", "false")] == "answer_chat"
    assert edges[("llm_reply", "source")] == "answer_llm"
    assert nodes["answer_llm"]["data"]["answer"] == "{{#llm_reply.text#}}"
    assert nodes["answer_chat"]["data"]["answer"] == "{{#extract_reply.reply#}}"


def test_clean_reply_drops_model_reasoning():
    from app.modules.student.assistant_speak import model_text, visible_sentences
    raw = (
        "<think>\n<!--dify-deepseek-reasoning-->学生说的是老师针对他，需要直接回答。\n<｜end▁of▁thinking｜>"
        "听着确实挺憋屈的，能说说是哪门课、哪位老师吗？"
    )
    assert visible_sentences("<think>不应输出。") == ""
    assert model_text(raw) == "听着确实挺憋屈的，能说说是哪门课、哪位老师吗？"
    assert model_text("已经帮你交上病假了。") == "已经帮你交上病假了。"


def test_flow_failure_answers_are_not_shown_to_students():
    assert assistant_dify._looks_like_flow_failure(
        "Run failed: Request failed with status code 503"
    )
    assert assistant_dify._looks_like_flow_failure("暂时没有得到有效回复。")
    assert not assistant_dify._looks_like_flow_failure(
        "已经帮你交上病假了，从2026-11-17 09:00到2026-11-19 18:00。"
    )


def test_ask_dify_rejects_flow_error_answer(monkeypatch):
    import asyncio

    import pytest

    from app.core.config import Settings
    from app.core.exceptions import BusinessError

    monkeypatch.setattr(
        assistant_dify,
        "get_settings",
        lambda: Settings(_env_file=None, stu_dify_api_key="test-key"),
    )

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            return None

        def json(self):
            return {"answer": "Run failed: Request failed with status code 503"}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, *args, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(assistant_dify.httpx, "AsyncClient", FakeClient)
    with pytest.raises(BusinessError) as exc:
        asyncio.run(
            assistant_dify.ask_dify(
                query="查进度",
                access_token="tok",
                history=[],
                user_key="student_1",
            )
        )
    assert exc.value.status_code == 502


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
