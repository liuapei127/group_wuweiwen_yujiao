"""Isolated stream integrity regressions: no database or live Dify calls."""
import asyncio

import httpx
import pytest
from pydantic import SecretStr

from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.modules.student import assistant_dify
from app.modules.student.assistant_reply_stream import ReplyGate


def call_reply(monkeypatch, upstream, *, kind="general", query="马云是谁", history=None):
    monkeypatch.setattr(get_settings(), "stu_dify_api_key", SecretStr("isolated-v6-key"))
    monkeypatch.setattr(assistant_dify, "chat_messages", upstream)
    seen = []
    async def run():
        return await assistant_dify.stream_reply(
            query=query, context={}, history=history or [], memories=[], user_key="isolated_student",
            country="Germany", reviewed_reply="", kind=kind, on_text=seen.append,
            first_content_timeout=6, overall_timeout=12,
        )
    return run, seen


@pytest.mark.parametrize("failure", ["timeout", "disconnect", "bad_tail", "bad_final", "rewritten_final"])
def test_safe_prefix_survives_later_failure_without_emitting_unchecked_tail(monkeypatch, failure):
    safe = "马云是阿里巴巴集团的联合创始人。"
    async def upstream(_url, _key, _timeout, _payload, publish, **budgets):
        assert budgets == {"first_content_timeout": 6, "overall_timeout": 12}
        publish(safe)
        publish(safe + "尚未完成的尾巴")
        if failure == "timeout":
            raise TimeoutError("isolated")
        if failure == "disconnect":
            raise httpx.ReadError("isolated")
        if failure == "bad_tail":
            publish(safe + "请拨打123456。")
        if failure == "rewritten_final":
            return {"answer": "你好呀，我在。"}
        return {"answer": safe + "请拨打123456"}
    run, seen = call_reply(monkeypatch, upstream)
    with pytest.raises(BusinessError) as caught:
        asyncio.run(run())
    error = caught.value
    assert getattr(error, "safe_partial", None) == safe
    assert getattr(error, "reason_code", None)
    assert seen == [safe]


def test_bad_first_sentence_emits_nothing_and_partial_is_empty(monkeypatch):
    async def upstream(_url, _key, _timeout, _payload, publish, **_):
        publish("请拨打123456。")
        pytest.fail("A rejected upstream sentence must stop generation")
    run, seen = call_reply(monkeypatch, upstream)
    with pytest.raises(BusinessError) as caught:
        asyncio.run(run())
    assert getattr(caught.value, "safe_partial", None) == ""
    assert seen == []


def test_general_biography_can_finish_with_public_years(monkeypatch):
    answer = "马云出生于1964年，是阿里巴巴集团的联合创始人。1999年，他与团队创办阿里巴巴。"
    async def upstream(_url, _key, _timeout, payload, publish, **_):
        assert '"kind": "general"' in payload["inputs"]["reply_context_json"]
        publish(answer)
        return {"answer": answer}
    run, seen = call_reply(monkeypatch, upstream)
    assert asyncio.run(run()) == answer
    assert seen[-1] == answer


@pytest.mark.parametrize("kind", ["general", "chat", "support"])
@pytest.mark.parametrize("answer", [
    "需要时请拨打110。", "警方热线：999。", "电话号码是1234。",
    "详情见https://unverified.invalid/help。", "详情见www.unverified.invalid。",
    "你的学校是某某大学。", "你已经入学了。", "你现在在德国生活。",
    "我可以帮你预约医院。", "建议你服用这种药。", "你这是焦虑症。",
])
def test_general_keeps_contacts_personal_facts_and_medical_guard(kind, answer):
    seen = []
    gate = ReplyGate(kind=kind, reviewed_reply="", query="马云是谁", history=[], on_text=seen.append)
    with pytest.raises(BusinessError):
        gate.accept(answer)
        gate.finish(answer)
    assert seen == []


@pytest.mark.parametrize("query,history,answer", [
    ("我其实还没入学", [{"role": "user", "content": "我已经入学"}], "你已经入学了。"),
    ("我现在在新加坡", [{"role": "user", "content": "我现在在德国"}], "你现在在德国生活。"),
])
def test_general_never_uses_old_stage_over_latest_correction(query, history, answer):
    seen = []
    gate = ReplyGate(kind="general", reviewed_reply="", query=query, history=history, on_text=seen.append)
    with pytest.raises(BusinessError):
        gate.accept(answer)
    assert not seen


def test_safe_sentence_in_same_chunk_is_preserved_before_bad_sentence(monkeypatch):
    safe = "我们可以先梳理你的问题。"
    async def upstream(_url, _key, _timeout, _payload, publish, **_):
        publish(safe + "请拨打123456。")
    run, seen = call_reply(monkeypatch, upstream)
    with pytest.raises(BusinessError) as caught:
        asyncio.run(run())
    assert getattr(caught.value, "safe_partial", None) == safe
    assert seen == [safe]


def test_checked_stream_cannot_be_rewritten_by_upstream(monkeypatch):
    safe = "我们可以先梳理你的问题。"
    async def upstream(_url, _key, _timeout, _payload, publish, **_):
        publish(safe)
        publish("你好呀，我在。")
    run, seen = call_reply(monkeypatch, upstream)
    with pytest.raises(BusinessError) as caught:
        asyncio.run(run())
    assert getattr(caught.value, "safe_partial", None) == safe
    assert seen == [safe]


def test_old_chat_numeric_policy_and_ask_review_remain_strict():
    gate = ReplyGate(kind="chat", reviewed_reply="", query="马云是谁", history=[], on_text=lambda _: None)
    with pytest.raises(BusinessError):
        gate.finish("马云出生于1964年。")
    gate = ReplyGate(kind="ask", reviewed_reply="请核对路线。", query="交通", history=[], on_text=lambda _: None)
    with pytest.raises(BusinessError):
        gate.finish("请核对路线。票价2元。")


def test_cancelled_reply_is_not_converted_to_recoverable_error(monkeypatch):
    async def upstream(*_, **__):
        raise asyncio.CancelledError
    run, seen = call_reply(monkeypatch, upstream)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(run())
    assert not seen


@pytest.mark.parametrize("answer", [
    "热线：\n999。", "需要帮助时call 999。", "请拨打一一零。",
    "详情见unverified.example.com。", "建议你\n服用这种药。",
])
def test_general_cannot_bypass_sensitive_guards_with_formatting(answer):
    gate = ReplyGate(kind="general", reviewed_reply="", query="普通问答", history=[], on_text=lambda _: None)
    with pytest.raises(BusinessError):
        gate.finish(answer)


@pytest.mark.parametrize("query", ["我还在国内", "我还没出国", "我尚未离境"])
@pytest.mark.parametrize("answer", ["你现在在德国生活。", "你已经在德国生活。"])
def test_latest_domestic_location_overrides_older_abroad_report(query, answer):
    gate = ReplyGate(kind="general", reviewed_reply="", query=query,
        history=[{"role": "user", "content": "我已经在德国"}], on_text=lambda _: None)
    with pytest.raises(BusinessError):
        gate.finish(answer)


@pytest.mark.parametrize("answer", ["你已经在 德国生活。", "你 已经入学了。"])
def test_whitespace_cannot_bypass_unverified_student_stage(answer):
    gate = ReplyGate(kind="general", reviewed_reply="", query="我还 在国内", history=[], on_text=lambda _: None)
    with pytest.raises(BusinessError):
        gate.finish(answer)


@pytest.mark.parametrize("answer", ["Intel成立于1968年。", "他在1999年的演讲中使用了recall这个单词。"])
def test_general_contact_guard_does_not_confuse_ordinary_english_words(answer):
    seen = []
    gate = ReplyGate(kind="general", reviewed_reply="", query="一般公司和语言问答", history=[], on_text=seen.append)
    assert gate.finish(answer) == answer
    assert seen == [answer]


@pytest.mark.parametrize("query,answer", [
    ("我现在在德国吗？", "你现在在德国生活。"),
    ("我现在在德国？", "你现在在德国生活。"),
    ("我已经入学了吗？", "你已经入学了。"),
    ("我已经入学了吗", "你已经入学了。"),
])
def test_student_stage_question_is_not_affirmative_evidence(query, answer):
    gate = ReplyGate(kind="general", reviewed_reply="", query=query, history=[], on_text=lambda _: None)
    with pytest.raises(BusinessError):
        gate.finish(answer)


def test_explicit_location_statement_can_precede_a_separate_question():
    gate = ReplyGate(kind="support", reviewed_reply="", query="我刚到德国，怎么总是想家？", history=[], on_text=lambda _: None)
    assert gate.finish("你刚到德国，可能还在适应。")
