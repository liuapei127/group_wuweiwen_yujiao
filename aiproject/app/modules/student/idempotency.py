"""Replay guard for the Dify thin shell.

Dify 的 HTTP 节点在失败时会重试 ``/api/v1/student/assistant/run``，而这条路径
会真的提交请假和投诉（投诉没有服务端去重）。同一学生、同一轮对话在短时间内
重复到达时直接返回上一次的答复，避免重复建单，也避免学生看到「今天已提交过
相同时间段」这种重试痕迹。

只保留已完成的结果，进程内缓存，不跨学生复用：key 含学生 ID 与完整请求摘要。
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import OrderedDict
from typing import Any, Callable

TTL_SECONDS = 60.0
MAX_ENTRIES = 512


class ReplayCache:
    def __init__(self, ttl: float = TTL_SECONDS, max_entries: int = MAX_ENTRIES) -> None:
        self.ttl = ttl
        self.max_entries = max_entries
        self._items: OrderedDict[str, tuple[float, dict[str, Any]]] = OrderedDict()
        self._lock = threading.Lock()

    def key(self, student_id: int, query: str, history: list | None) -> str:
        payload = json.dumps(
            {"q": (query or "").strip(), "h": history or []},
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
        return f"{student_id}:{digest}"

    def get(self, key: str) -> dict[str, Any] | None:
        now = time.monotonic()
        with self._lock:
            hit = self._items.get(key)
            if hit is None:
                return None
            stored_at, value = hit
            if now - stored_at > self.ttl:
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
        """Return ``(response, replayed)``; ``produce`` runs at most once per key."""
        cached = self.get(key)
        if cached is not None:
            return cached, True
        value = produce()
        self.put(key, value)
        return value, False


_cache = ReplayCache()


def replay_cache() -> ReplayCache:
    return _cache
