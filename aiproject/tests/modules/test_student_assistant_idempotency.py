"""Dify 重试防护：同一轮请求只执行一次业务。"""

import asyncio
from concurrent.futures import Future, ThreadPoolExecutor
from threading import Event

import pytest

from app.core.exceptions import BusinessError
from app.modules.student import assistant_session, idempotency
from app.modules.student.idempotency import ReplayCache
from app.modules.student.schemas import AssistantTurn


def test_same_turn_runs_once():
    cache = ReplayCache()
    calls = []

    def produce():
        calls.append(1)
        return {"reply": "已经帮你交上病假了"}

    key = cache.key(7, "我要请假", [{"role": "user", "content": "病假"}])
    first, replayed = cache.remember(key, produce)
    second, replay2 = cache.remember(key, produce)
    assert first == second == {"reply": "已经帮你交上病假了"}
    assert (replayed, replay2) == (False, True)
    assert len(calls) == 1


def test_different_students_or_queries_are_separate():
    cache = ReplayCache()
    a = cache.key(1, "查进度", [])
    assert a != cache.key(2, "查进度", [])
    assert a != cache.key(1, "查请假", [])
    assert a != cache.key(1, "查进度", [{"role": "user", "content": "上一轮"}])
    cache.put(a, {"reply": "A"})
    assert cache.get(cache.key(2, "查进度", [])) is None


def test_entries_expire(monkeypatch):
    cache = ReplayCache(ttl=0.01)
    key = cache.key(1, "查进度", [])
    cache.put(key, {"reply": "A"})
    import time

    time.sleep(0.05)
    assert cache.get(key) is None


def test_cache_is_bounded():
    cache = ReplayCache(max_entries=2)
    for i in range(5):
        cache.put(cache.key(1, f"q{i}", []), {"reply": str(i)})
    assert cache.get(cache.key(1, "q0", [])) is None
    assert cache.get(cache.key(1, "q4", [])) == {"reply": "4"}


def test_failures_are_not_cached():
    cache = ReplayCache()
    key = cache.key(1, "我要请假", [])

    def boom():
        raise RuntimeError("业务失败")

    try:
        cache.remember(key, boom)
    except RuntimeError:
        pass
    assert cache.get(key) is None


def test_concurrent_replays_share_execution_and_keep_other_turns_independent(monkeypatch):
    waiter_arrived = Event()

    class ObservedFuture(Future):
        def result(self, timeout=None):
            waiter_arrived.set()
            return super().result(timeout=timeout)

    monkeypatch.setattr(idempotency, "Future", ObservedFuture)
    cache = ReplayCache()
    key = cache.key(7, "投诉详情", [])
    started = Event()
    release = Event()
    response = {"reply": "已提交投诉"}

    def submit():
        started.set()
        assert release.wait(5)
        return response

    def duplicate():
        pytest.fail("同轮投诉执行了第二次")

    with ThreadPoolExecutor(max_workers=3) as executor:
        owner = executor.submit(cache.remember, key, submit)
        try:
            assert started.wait(5)
            waiter = executor.submit(cache.remember, key, duplicate)
            assert waiter_arrived.wait(5)
            other = executor.submit(cache.remember, cache.key(8, "投诉详情", []), lambda: response)
            assert other.result(2) == (response, False)
        finally:
            release.set()
        assert owner.result(2) == (response, False)
        assert waiter.result(2) == (response, True)


def test_dify_failure_after_callback_reuses_the_existing_business_result(monkeypatch):
    from app.core.config import Settings
    monkeypatch.setattr("app.core.config.get_settings", lambda: Settings(_env_file=None, stu_assistant_mode="legacy"))
    cache = ReplayCache()
    calls = []
    stored = []
    history = [{"role": "assistant", "content": "请补充情况" + "。" * 4500 + "  "}]
    query = "老师在上课时多次打断我回答问题"
    result = {"reply": "已提交正式投诉", "intent": "feedback", "data": {"id": 7}}

    def execute(*args, **kwargs):
        calls.append(kwargs["message"])
        return result

    async def dify_times_out(**kwargs):
        callback_history = [
            AssistantTurn(role=turn["role"], content=turn["content"].strip()[:4000]).model_dump()
            for turn in kwargs["history"]
        ]
        key = cache.key(7, kwargs["query"], callback_history)
        cache.remember(key, lambda: execute(message=kwargs["query"]))
        raise BusinessError(502, "Dify 调用超时")

    monkeypatch.setattr(assistant_session, "replay_cache", lambda: cache)
    monkeypatch.setattr(assistant_session.assistant_dify, "ask_dify", dify_times_out)
    monkeypatch.setattr(assistant_session.assistant_chat, "handle_chat", execute)
    monkeypatch.setattr(assistant_session.assistant_mem0, "search_memories", lambda *a, **kw: [])
    monkeypatch.setattr(assistant_session.assistant_mem0, "remember_turn", lambda *a, **kw: None)
    monkeypatch.setattr(assistant_session.assistant_store, "create_conversation", lambda *a, **kw: {"id": "conversation"})
    monkeypatch.setattr(assistant_session.assistant_store, "recent_turns", lambda *a, **kw: history)
    monkeypatch.setattr(assistant_session.assistant_store, "append_turn", lambda *a, **kw: stored.append(kw))

    reply = asyncio.run(assistant_session.run_turn(
        object(), student_id=7, query=query, conversation_id=None, access_token="test", use_dify=True
    ))

    assert calls == [query]
    assert reply["answer"] == result["reply"]
    assert reply["data"] == {"id": 7, "source": "local_fallback"}
    assert len(stored) == 1 and stored[0]["user_text"] == query
