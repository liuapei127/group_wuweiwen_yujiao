"""Context/continuation tests use an isolated upstream, never a live crisis turn."""
import asyncio
import json

import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.modules.student import assistant_dify
from app.modules.student.assistant_reply_stream import ReplyGate


def test_visible_request_contains_role_paired_history_and_distinct_context_sources(monkeypatch):
    history = [{"role": "user", "content": "我一个人"}, {"role": "assistant", "content": "先到有人在的地方。"}]
    official = {"profile": {"abroad_country": "Germany"}, "position": {"known": False}}
    safety = {"active": True, "alone": True, "safety": "unknown", "self_reported_location": "纽约"}
    seen = []
    monkeypatch.setattr(get_settings(), "stu_dify_api_key", SecretStr("isolated-v7"))
    async def upstream(_url, _key, _timeout, payload, publish, **budgets):
        value = json.loads(payload["inputs"]["reply_context_json"])
        assert value["recent_user_context"] == history
        assert value["student_context"] == official
        assert value["self_reported_memories"] == ["学生姓名：小木"]
        assert value["safety_context"] == safety
        assert value["initial_prefix"] == "你说你现在一个人，请先到有人在的安全地方。"
        assert value["response_instructions"]["continue_after_prefix"] is True
        assert payload["user"] == "stu_2"
        assert "student_access_token" not in payload["inputs"]
        assert budgets == {"first_content_timeout": 12, "overall_timeout": 15}
        publish("你可以先给信任的朋友发条消息，请他现在陪你。")
        return {"answer": "你可以先给信任的朋友发条消息，请他现在陪你。"}
    monkeypatch.setattr(assistant_dify, "chat_messages", upstream)
    result = asyncio.run(assistant_dify.stream_reply(query="我在纽约", context=official, history=history,
        memories=["学生姓名：小木"], user_key="stu_2", country="Germany", reviewed_reply="请先确保安全。",
        kind="safety_support", on_text=seen.append, safety_context=safety,
        initial_prefix="你说你现在一个人，请先到有人在的安全地方。", first_content_timeout=12, overall_timeout=15))
    assert result == "你说你现在一个人，请先到有人在的安全地方。你可以先给信任的朋友发条消息，请他现在陪你。"
    assert seen == [result]


@pytest.mark.parametrize("failure", ["timeout", "bad_tail", "rewritten_final", "blank_final"])
def test_trusted_safety_prefix_survives_failed_continuation(monkeypatch, failure):
    prefix = "你说你现在一个人，请先到有人在的安全地方。"
    seen = []
    monkeypatch.setattr(get_settings(), "stu_dify_api_key", SecretStr("isolated-v7"))
    async def upstream(_url, _key, _timeout, payload, publish, **_):
        if failure == "timeout":
            raise TimeoutError("isolated")
        if failure == "bad_tail":
            publish("我现在就帮你找当地资源。")
        if failure == "rewritten_final":
            publish("你可以联系一个信任的人。")
            return {"answer": "你好呀。"}
        return {"answer": ""}
    monkeypatch.setattr(assistant_dify, "chat_messages", upstream)
    with pytest.raises(BusinessError) as caught:
        asyncio.run(assistant_dify.stream_reply(query="我一个人", context={}, history=[], memories=[],
            user_key="stu_2", country="", reviewed_reply=prefix, kind="safety_support", on_text=seen.append,
            safety_context={"active": True, "alone": True}, initial_prefix=prefix))
    expected = prefix + ("你可以联系一个信任的人。" if failure == "rewritten_final" else "")
    assert getattr(caught.value, "safe_partial", None) == expected
    assert not any("找当地资源" in text for text in seen)
    assert not any(not text.startswith(prefix) for text in seen)


def test_missing_provider_configuration_retains_trusted_safety_prefix(monkeypatch):
    monkeypatch.setattr(get_settings(), "stu_dify_api_key", SecretStr(""))
    with pytest.raises(BusinessError) as caught:
        asyncio.run(assistant_dify.stream_reply(query="我一个人", context={}, history=[], memories=[],
            user_key="stu_2", country="", reviewed_reply="", kind="safety_support", on_text=lambda _: None,
            safety_context={"active": True}, initial_prefix="请先到有人在的安全地方。"))
    assert getattr(caught.value, "safe_partial", None) == "请先到有人在的安全地方。"


def test_model_may_echo_exact_initial_prefix_once_without_duplication():
    seen = []
    prefix = "请先到有人在的安全地方。"
    gate = ReplyGate(kind="safety_support", reviewed_reply="", query="我一个人", history=[], on_text=seen.append,
        safety_context={"alone": True}, initial_prefix=prefix)
    gate.accept(prefix + "你可以先联系一个信任的人。")
    assert gate.finish(prefix + "你可以先联系一个信任的人。") == prefix + "你可以先联系一个信任的人。"
    assert seen == [prefix + "你可以先联系一个信任的人。"]


def test_continuation_can_share_initial_words_without_being_a_rewritten_prefix():
    seen = []
    prefix = "请先到有人在的安全地方。"
    gate = ReplyGate(kind="safety_support", reviewed_reply="", query="我一个人", history=[], on_text=seen.append,
        safety_context={"alone": True}, initial_prefix=prefix)
    gate.accept("请先")
    assert not seen
    gate.accept("请先联系一位信任的朋友。")
    assert gate.finish("请先联系一位信任的朋友。") == prefix + "请先联系一位信任的朋友。"


def test_echoed_prefix_cannot_be_changed_after_a_checked_continuation():
    prefix = "请先到有人在的安全地方。"
    gate = ReplyGate(kind="safety_support", reviewed_reply="", query="我一个人", history=[], on_text=lambda _: None,
        safety_context={"alone": True}, initial_prefix=prefix)
    gate.accept(prefix + "你可以联系一个信任的人。")
    with pytest.raises(BusinessError):
        gate.finish("请先去别的地方。你可以联系一个信任的人。")
    assert gate.visible == prefix + "你可以联系一个信任的人。"


@pytest.mark.parametrize("text", [
    "你身边有人可以陪你吗？", "你现在是一个人吗？", "有人在你身边吗？",
    "我现在就帮你找当地支持资源。", "我会帮你查询稍后给你。", "我已经联系了老师。",
    "你现在可以拨打123456。", "你这是抑郁症。",
])
@pytest.mark.parametrize("alone", [True, False])
def test_safety_generation_does_not_repeat_known_facts_or_invent_actions(text, alone):
    seen = []
    gate = ReplyGate(kind="safety_support", reviewed_reply="", query="我一个人", history=[], on_text=seen.append,
        safety_context={"alone": alone}, initial_prefix="")
    with pytest.raises(BusinessError):
        gate.accept(text)
        gate.finish(text)
    assert not seen


def test_safety_can_ask_for_available_contact_not_reask_current_companionship():
    gate = ReplyGate(kind="safety_support", reviewed_reply="", query="我一个人", history=[], on_text=lambda _: None,
        safety_context={"alone": True})
    assert gate.finish("有没有一位你信任的人可以现在联系？") == "有没有一位你信任的人可以现在联系？"


def test_trusted_prefix_does_not_authorize_a_generated_phone_or_official_fact():
    prefix = "后端已经核实的参考内容。"
    for text in ["请拨打123456。", "你的学校是测试大学。", "我来帮你查找资源。"]:
        gate = ReplyGate(kind="safety_support", reviewed_reply="", query="我一个人", history=[], on_text=lambda _: None,
            safety_context={"alone": True}, initial_prefix=prefix)
        with pytest.raises(BusinessError):
            gate.accept(text)
        assert gate.visible == prefix


def test_cancellation_propagates_with_an_initial_prefix(monkeypatch):
    monkeypatch.setattr(get_settings(), "stu_dify_api_key", SecretStr("isolated-v7"))
    async def cancelled(*_, **__):
        raise asyncio.CancelledError
    monkeypatch.setattr(assistant_dify, "chat_messages", cancelled)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(assistant_dify.stream_reply(query="我一个人", context={}, history=[], memories=[],
            user_key="stu_2", country="", reviewed_reply="", kind="safety_support", on_text=lambda _: None,
            safety_context={"active": True}, initial_prefix="请先到有人在的安全地方。"))


@pytest.mark.parametrize("current,claim", [
    (None, "你现在在纽约。"), (None, "你在美国。"),
    ("纽约", "你现在在德国。"), ("纽约", "你现在在新加坡。"),
    ("新加坡", "你现在在纽约。"), ("德国", "你现在在美国。"),
])
def test_safety_place_claim_uses_only_current_conversation_location(current, claim):
    gate = ReplyGate(kind="safety_support", reviewed_reply="", query="我一个人",
        history=[{"role": "user", "content": "我以前在德国"}], on_text=lambda _: None,
        safety_context={"self_reported_location": current})
    with pytest.raises(BusinessError):
        gate.finish(claim)


@pytest.mark.parametrize("current,claim", [
    ("纽约", "你说你在纽约，我们先找能陪伴你的人。"),
    ("纽约", "你在美国，我们先确认当下安全。"),
    ("德国", "你说你在德国，我们先确认当下安全。"),
    ("新加坡", "你说你在新加坡，我们先确认当下安全。"),
])
def test_safety_place_claim_can_reflect_explicit_current_self_report(current, claim):
    gate = ReplyGate(kind="safety_support", reviewed_reply="", query="我一个人", history=[], on_text=lambda _: None,
        safety_context={"self_reported_location": current})
    assert gate.finish(claim) == claim


def test_typed_new_york_self_report_overrides_old_germany_and_does_not_imply_arrival():
    context = {"self_reported_location": {"country": "US", "city": "New York", "label": "纽约", "evidence": "我在纽约"}}
    for claim in ["你在纽约。", "你在美国。"]:
        gate = ReplyGate(kind="safety_support", reviewed_reply="", query="我一个人", history=[], on_text=lambda _: None,
            safety_context=context)
        assert gate.finish(claim) == claim
    for claim in ["你现在在德国。", "你已经入学。"]:
        gate = ReplyGate(kind="safety_support", reviewed_reply="", query="我一个人",
            history=[{"role": "user", "content": "我在德国"}], on_text=lambda _: None, safety_context=context)
        with pytest.raises(BusinessError):
            gate.finish(claim)


def test_current_us_country_alone_does_not_prove_new_york_city():
    gate = ReplyGate(kind="safety_support", reviewed_reply="", query="我一个人", history=[], on_text=lambda _: None,
        safety_context={"self_reported_location": {"country": "US", "city": None, "label": "美国", "evidence": "我在美国"}})
    with pytest.raises(BusinessError):
        gate.finish("你在纽约。")


def test_plain_chat_capability_description_keeps_legacy_behavior():
    gate = ReplyGate(kind="chat", reviewed_reply="", query="你可以做什么", history=[], on_text=lambda _: None)
    assert gate.finish("我可以帮你查询申请进度。") == "我可以帮你查询申请进度。"
