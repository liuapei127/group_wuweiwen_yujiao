"""A read timeout must not become an unlimited wait while Dify sends heartbeats."""
import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.ai.dify_stream import chat_messages
from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.modules.student import assistant_dify


def frame(event, **fields):
    return ("data: " + json.dumps({"event": event, **fields}, ensure_ascii=False) + "\n\n").encode()


class ScriptedStream(httpx.AsyncByteStream):
    def __init__(self, script):
        self.script = script
        self.closed = False
        self.emitted = 0

    async def __aiter__(self):
        for delay, value in self.script:
            await asyncio.sleep(delay)
            if isinstance(value, Exception):
                raise value
            self.emitted += 1
            yield value

    async def aclose(self):
        self.closed = True


def install_stream(monkeypatch, stream):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **options: real_client(
        **options, transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=stream))))


def test_first_content_deadline_ignores_heartbeats_and_empty_answers(monkeypatch):
    stream = ScriptedStream([(0, frame("message", answer="")), (0, frame("message", answer=" "))]
                            + [(0.01, b": ping\n\n")] * 100)
    install_stream(monkeypatch, stream)
    with pytest.raises(TimeoutError):
        asyncio.run(chat_messages("http://dify.test/v1", "test", 20, {}, lambda _: None,
                                  first_content_timeout=0.045, overall_timeout=0.5))
    assert stream.closed
    assert stream.emitted < 20


def test_overall_deadline_still_applies_after_content_arrives(monkeypatch):
    stream = ScriptedStream([(0, frame("message", answer="你好。"))]
                            + [(0.01, b": ping\n\n")] * 100)
    install_stream(monkeypatch, stream)
    seen = []
    with pytest.raises(TimeoutError):
        asyncio.run(chat_messages("http://dify.test/v1", "test", 20, {}, seen.append,
                                  first_content_timeout=0.03, overall_timeout=0.07))
    assert seen == ["你好。"]
    assert stream.closed and stream.emitted < 20


def test_valid_content_retires_only_the_first_content_deadline(monkeypatch):
    stream = ScriptedStream([(0, frame("message", answer="你好。"))]
                            + [(0.01, b": ping\n\n")] * 7
                            + [(0, frame("message", answer="继续说。")), (0, frame("message_end"))])
    install_stream(monkeypatch, stream)
    seen = []
    result = asyncio.run(chat_messages("http://dify.test/v1", "test", 20, {}, seen.append,
                                      first_content_timeout=0.03, overall_timeout=0.4))
    assert result["answer"] == "你好。继续说。" and seen[-1] == result["answer"]
    assert stream.closed


def test_first_content_deadline_includes_waiting_for_response_headers(monkeypatch):
    real_client = httpx.AsyncClient
    cancelled = []

    async def handler(_):
        try:
            await asyncio.sleep(1)
        finally:
            cancelled.append(True)
        return httpx.Response(200, content=b"")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **options: real_client(
        **options, transport=httpx.MockTransport(handler)))
    with pytest.raises(TimeoutError):
        asyncio.run(chat_messages("http://dify.test/v1", "test", 20, {}, lambda _: None,
                                  first_content_timeout=0.035, overall_timeout=0.5))
    assert cancelled == [True]


def test_default_call_remains_compatible_and_network_errors_close_stream(monkeypatch):
    stream = ScriptedStream([(0, frame("message", answer="你好。")), (0, frame("message_end"))])
    install_stream(monkeypatch, stream)
    result = asyncio.run(chat_messages("http://dify.test/v1", "test", 20, {}, lambda _: None))
    assert result["answer"] == "你好。" and stream.closed


def test_network_error_closes_stream_without_leaving_a_producer(monkeypatch):
    stream = ScriptedStream([(0, frame("message", answer="第一句。")), (0, httpx.ReadError("test disconnect"))])
    install_stream(monkeypatch, stream)
    with pytest.raises(httpx.ReadError):
        asyncio.run(chat_messages("http://dify.test/v1", "test", 20, {}, lambda _: None,
                                  first_content_timeout=0.2, overall_timeout=0.4))
    assert stream.closed


def test_fact_guard_rejection_closes_the_same_upstream_request(monkeypatch):
    stream = ScriptedStream([(0, frame("message", answer="未核实信息。")), (1, b": ping\n\n")])
    install_stream(monkeypatch, stream)

    def reject(_):
        raise BusinessError(502, "回复需要核对事实")

    with pytest.raises(BusinessError):
        asyncio.run(chat_messages("http://dify.test/v1", "test", 20, {}, reject,
                                  first_content_timeout=0.2, overall_timeout=0.4))
    assert stream.closed and stream.emitted == 1


def test_cancel_closes_stream_and_propagates_cancelled_error(monkeypatch):
    stream = ScriptedStream([(0, frame("message", answer="第一句。")), (1, b": ping\n\n")])
    install_stream(monkeypatch, stream)

    async def check():
        started = asyncio.Event()
        task = asyncio.create_task(chat_messages("http://dify.test/v1", "test", 20, {},
                                                lambda _: started.set(), overall_timeout=2))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(check())
    assert stream.closed


def test_understanding_total_budget_maps_to_recoverable_business_error(monkeypatch):
    real_client = httpx.AsyncClient
    monkeypatch.setattr(get_settings(), "stu_dify_api_key", SecretStr("deadline-test-key"))
    cancelled = []

    async def handler(_):
        try:
            await asyncio.sleep(1)
        finally:
            cancelled.append(True)
        return httpx.Response(200, json={"answer": '{"intent":"chat"}'})

    monkeypatch.setattr(httpx, "AsyncClient", lambda **options: real_client(
        **options, transport=httpx.MockTransport(handler)))
    with pytest.raises(BusinessError) as error:
        asyncio.run(assistant_dify.understand(query="hello", history=[], context={}, task=None,
            memories=[], user_key="stu_test", overall_timeout=0.035))
    assert error.value.status_code == 502 and cancelled == [True]


def test_visible_reply_forwards_opt_in_budgets_and_maps_timeout(monkeypatch):
    monkeypatch.setattr(get_settings(), "stu_dify_api_key", SecretStr("deadline-test-key"))
    forwarded = []

    async def upstream(*args, **kwargs):
        forwarded.append(kwargs)
        raise TimeoutError

    monkeypatch.setattr(assistant_dify, "chat_messages", upstream)
    with pytest.raises(BusinessError) as error:
        asyncio.run(assistant_dify.stream_reply(query="hello", context={}, history=[], memories=[],
            user_key="stu_test", country="Germany", reviewed_reply="你好。", kind="chat", on_text=lambda _: None,
            first_content_timeout=6, overall_timeout=12))
    assert error.value.status_code == 502
    assert forwarded == [{"first_content_timeout": 6, "overall_timeout": 12}]
