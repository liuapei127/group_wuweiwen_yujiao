"""Real upstream deltas, fact checks and business boundaries of visible replies."""
import asyncio
import json
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import text

from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.modules.student import assistant_dify, assistant_workspace as workspace
from app.modules.student.assistant_reply_stream import ReplyGate, safe_context_reply
from app.modules.student.schemas import AssistantUnderstanding
from tests.modules.test_student_workspace import db, prepare_turn


def test_upstream_sentences_are_visible_before_generation_finishes(monkeypatch):
    monkeypatch.setattr(get_settings(), "stu_dify_api_key", SecretStr("stream-test-key"))
    seen = []

    async def upstream(url, key, timeout, payload, on_text):
        assert payload["inputs"]["response_stage"] == "reply"
        assert "student_access_token" not in payload["inputs"]
        on_text("你可以先说说")
        assert seen == []  # An incomplete sentence has not passed the guard yet.
        on_text("你可以先说说。")
        assert seen == ["你可以先说说。"]  # The upstream request has not returned.
        await asyncio.sleep(0)
        on_text("你可以先说说。我们一起梳理。")
        assert len(seen) == 2
        return {"answer": "你可以先说说。我们一起梳理。"}

    monkeypatch.setattr(assistant_dify, "chat_messages", upstream)
    result = asyncio.run(assistant_dify.stream_reply(
        query="最近有点想家", context={"profile": {"abroad_country": "Germany"}},
        history=[], memories=[], user_key="stu_2", country="Germany",
        reviewed_reply="我在听。", kind="support", on_text=seen.append,
    ))
    assert result == seen[-1]


def test_reviewed_knowledge_rejects_new_facts_before_they_are_emitted():
    seen = []
    gate = ReplyGate(kind="ask", reviewed_reply="需要警方帮助时拨打110。", query="报警电话", history=[], on_text=seen.append)
    gate.accept("需要警方帮助时拨打110。")
    assert seen == ["需要警方帮助时拨打110。"]
    with pytest.raises(BusinessError):
        gate.accept("需要警方帮助时拨打110。也可以拨打123456。")
    assert all("123456" not in text for text in seen)


def test_knowledge_generation_cannot_silently_omit_remaining_steps():
    gate = ReplyGate(kind="ask", reviewed_reply="先核对路线。再按当地规则购票。", query="怎么坐地铁", history=[], on_text=lambda _: None)
    with pytest.raises(BusinessError, match="完整"):
        gate.finish("先核对路线。")


@pytest.mark.parametrize("fragment", ["10。", "110。", "第二步再买票。", "拨打1100。"])
def test_knowledge_stream_cannot_select_number_suffixes_or_reorder_reviewed_sentences(fragment):
    seen = []
    gate = ReplyGate(kind="ask", reviewed_reply="第一步核对路线。第二步再买票。紧急情况拨打110。", query="交通问题", history=[], on_text=seen.append)
    with pytest.raises(BusinessError):
        gate.accept(fragment)
    assert not seen


def test_workspace_forwards_checked_upstream_text_before_transcript_save(db, monkeypatch):
    prepare_turn(monkeypatch)
    monkeypatch.setattr(get_settings(), "stu_dify_api_key", SecretStr("stream-test-key"))
    async def understand(**kwargs):
        assert kwargs["stream_plan"]
        return AssistantUnderstanding(intent="support")
    seen = []
    async def upstream(_url, _key, _timeout, _payload, publish, **budgets):
        assert budgets["first_content_timeout"] == 12
        assert 0 < budgets["overall_timeout"] <= 15
        publish("你可以先说说。")
        assert seen == ["你可以先说说。"]
        assert db.scalar(text("SELECT COUNT(*) FROM stu_assistant_message")) == 0
        await asyncio.sleep(0)
        publish("你可以先说说。我们一起梳理。")
        return {"answer": "你可以先说说。我们一起梳理。"}
    monkeypatch.setattr(assistant_dify, "understand", understand)
    monkeypatch.setattr(assistant_dify, "chat_messages", upstream)
    result = asyncio.run(workspace.run_turn(db, student_id=2, query="我最近想家了", conversation_id=None, use_dify=True, on_text=seen.append))
    assert len(seen) == 2 and result["reply"] == seen[-1]


@pytest.mark.parametrize("reply", [
    '{"intent":"support","reply":"你好"}',
    "我已经帮你联系老师了。", "我可以帮你通知学校。",
    "尤其在刚到德国的时候。", "你已经入学了。", "你现在在新加坡生活。",
    "你的学校是测试大学。", "你是某某大学的学生。", "我可以帮你预约医院。",
    "有需要可以拨打110。",
])
def test_private_or_unsupported_claims_do_not_reach_visible_stream(reply):
    seen = []
    gate = ReplyGate(kind="support", reviewed_reply="我在听。", query="我想家了", history=[], on_text=seen.append)
    with pytest.raises(BusinessError):
        gate.accept(reply)
        gate.finish(reply)
    assert not seen


def test_destination_alone_never_authorizes_arrival_claim_but_explicit_self_report_does():
    assert safe_context_reply("你刚到德国，可能还在适应。", "我想家了", []) is None
    assert safe_context_reply("你刚到德国，可能还在适应。", "我刚到德国，有点想家", [])
    assert safe_context_reply("你已经入学了。", "我还没入学", []) is None
    assert safe_context_reply("你已经入学了。", "我其实还没入学", [{"role": "user", "content": "我已经入学"}]) is None
    assert safe_context_reply("你现在在德国生活。", "我现在在新加坡", [{"role": "user", "content": "我现在在德国"}]) is None


@pytest.mark.parametrize("query", ["我要坐地铁怎么坐", "坐MRT要准备什么", "U-Bahn怎么买票"])
def test_transport_stays_queryable_when_model_is_unavailable(query):
    assert workspace.local_understanding(query, None).intent == "ask"


def test_stream_failure_reports_unfinished_without_uncertified_partial_or_business_write(db, monkeypatch):
    prepare_turn(monkeypatch)
    async def understand(**kwargs):
        assert kwargs["stream_plan"] is True
        return AssistantUnderstanding(intent="support")
    calls=[]
    async def broken(**kwargs):
        calls.append(kwargs)
        assert kwargs["first_content_timeout"]==12 and 0 < kwargs["overall_timeout"]<=15
        kwargs["on_text"]("我们可以慢慢聊。")
        raise BusinessError(502, "upstream interrupted")
    monkeypatch.setattr(assistant_dify, "understand", understand)
    monkeypatch.setattr(assistant_dify, "stream_reply", broken)
    seen = []
    result = asyncio.run(workspace.run_turn(db, student_id=2, query="我想家了", conversation_id=None, use_dify=True, on_text=seen.append))
    assert seen[0] == "我们可以慢慢聊。" and "" not in seen
    assert len(calls)==1 and "未能完成" in result["reply"]
    assert result["reply"] != seen[0] and result["reply_notice"] == "回复中断，请重试"
    assert seen[-1] == result["reply"]
    assert result["task"] is None and result["source"] == "local_fallback"


def test_business_draft_never_enters_visible_reply_model(db, monkeypatch):
    prepare_turn(monkeypatch)
    async def understand(**kwargs):
        return AssistantUnderstanding(intent="leave_create")
    async def forbidden(**kwargs):
        pytest.fail("A business draft cannot be rewritten by the visible reply model")
    monkeypatch.setattr(assistant_dify, "understand", understand)
    monkeypatch.setattr(assistant_dify, "stream_reply", forbidden)
    seen = []
    result = asyncio.run(workspace.run_turn(db, student_id=2, query="我要请假", conversation_id=None, use_dify=True, on_text=seen.append))
    assert result["task"]["status"] == "collecting" and seen[-1] == result["reply"]


def test_canvas_visible_answer_is_bound_directly_to_reply_llm():
    path = Path(__file__).parents[2] / "docs/dify/local-integration/stu-workspace.yml"
    doc = json.loads(path.read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in doc["workflow"]["graph"]["nodes"]}
    assert nodes["visible_answer"]["data"]["answer"] == "{{#visible_reply.text#}}"
    assert not any(node["data"]["type"] == "http-request" for node in nodes.values())
    start = {v["variable"] for v in nodes["start"]["data"]["variables"]}
    assert {"response_stage", "reply_context_json"} <= start
    edges = {(e["source"], e["sourceHandle"]): e["target"] for e in doc["workflow"]["graph"]["edges"]}
    assert edges[("response_stage", "reply")] == "visible_reply"
    assert edges[("route", "source")] == "planning_done"
    assert edges[("planning_done", "plan")] == "answer_service"
