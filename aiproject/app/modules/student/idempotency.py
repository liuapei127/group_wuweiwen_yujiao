"""Replay guard for the Dify thin shell.

Dify 回调及官网的本地回退都可能执行同一轮对话。两条路径共用回放缓存，
避免 Dify 已经完成业务写入、但答复超时或失败后，官网再提交一次。

同一进程内，相同请求的并发调用等待首次执行完成。成功结果短期缓存，失败可重试。
按学生 ID 和请求内容区分，不跨学生复用。
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from concurrent.futures import Future
from typing import Any, Callable

TTL_SECONDS = 60.0
MAX_ENTRIES = 512


class ReplayCache:
    def __init__(self, ttl: float = TTL_SECONDS, max_entries: int = MAX_ENTRIES) -> None:
        self.ttl = ttl
        self.max_entries = max_entries
        self._items: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._pending: dict[str, Future[dict[str, Any]]] = {}
        self._lock = threading.Lock()

    def key(
        self, student_id: int, query: str, history: list | None, *, mock_country: str | None = None
    ) -> str:
        # Match the Dify callback, which trims history and forwards at most 4000 characters per turn.
        turns = [
            {"role": turn["role"], "content": turn["content"].strip()[:4000].strip()}
            for turn in (history or [])[-12:]
            if turn["content"].strip()
        ]
        payload = json.dumps(
            {"q": (query or "").strip(), "h": turns, "mock_country": mock_country},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
        return f"{student_id}:{digest}"

    def get(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            return self._get_locked(key)

    def _get_locked(self, key: str) -> dict[str, Any] | None:
        hit = self._items.get(key)
        if hit is None:
            return None
        stored_at, value = hit
        if time.monotonic() - stored_at > self.ttl:
            self._items.pop(key, None)
            return None
        self._items.move_to_end(key)
        return value

    def put(self, key: str, value: dict[str, Any]) -> None:
        with self._lock:
            self._items[key] = (time.monotonic(), value)
            self._items.move_to_end(key)
            while len(self._items) > self.max_entries:
                self._items.popitem(last=False)

    def remember(self, key: str, produce: Callable[[], dict[str, Any]]) -> tuple[dict[str, Any], bool]:
        """Return the result and whether it was produced by another call."""
        with self._lock:
            cached = self._get_locked(key)
            if cached is not None:
                return cached, True
            pending = self._pending.get(key)
            first = pending is None
            if pending is None:
                pending = Future()
                self._pending[key] = pending

        if not first:
            return pending.result(), True

        try:
            value = produce()
            self.put(key, value)
        except BaseException as exc:
            pending.set_exception(exc)
            raise
        else:
            pending.set_result(value)
            return value, False
        finally:
            with self._lock:
                self._pending.pop(key)


_cache = ReplayCache()


def replay_cache() -> ReplayCache:
    return _cache
