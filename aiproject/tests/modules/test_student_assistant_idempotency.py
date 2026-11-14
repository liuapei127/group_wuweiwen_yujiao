"""Dify 重试防护：同一轮请求只执行一次业务。"""

from app.modules.student.idempotency import ReplayCache


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
