"""客服 /api/cs/chat 容量控制（进程内；多副本需网关或 Redis 分布式限流）。"""
from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.core.config import get_settings


class CsChatCapacity:
    def __init__(
        self,
        max_concurrent: int,
        queue_timeout_sec: float,
        rate_per_minute_per_ip: int,
    ) -> None:
        self.max_concurrent = max_concurrent
        self.queue_timeout_sec = queue_timeout_sec
        self.rate_per_minute_per_ip = rate_per_minute_per_ip
        self._sem = (
            asyncio.Semaphore(max_concurrent) if max_concurrent > 0 else None
        )
        self._ip_hits: OrderedDict[str, list[float]] = OrderedDict()

    def _rate_ok(self, client_ip: str) -> bool:
        if self.rate_per_minute_per_ip <= 0:
            return True
        now = time.monotonic()
        window = 60.0
        while self._ip_hits and now - next(iter(self._ip_hits.values()))[-1] >= window:
            self._ip_hits.popitem(last=False)
        if client_ip not in self._ip_hits and len(self._ip_hits) >= 10_000:
            return False
        hits = [t for t in self._ip_hits.get(client_ip, []) if now - t < window]
        if len(hits) >= self.rate_per_minute_per_ip:
            self._ip_hits[client_ip] = hits
            return False
        hits.append(now)
        self._ip_hits[client_ip] = hits
        self._ip_hits.move_to_end(client_ip)
        return True

    @asynccontextmanager
    async def slot(self, client_ip: str) -> AsyncIterator[None]:
        if not self._rate_ok(client_ip or "unknown"):
            raise CsCapacityExceeded(
                "请求过于频繁，请稍后再试"
            )
        if self._sem is None:
            yield
            return
        try:
            await asyncio.wait_for(
                self._sem.acquire(), timeout=self.queue_timeout_sec
            )
        except asyncio.TimeoutError as exc:
            raise CsCapacityExceeded(
                "当前咨询人数较多，请稍后重试"
            ) from exc
        try:
            yield
        finally:
            self._sem.release()


class CsCapacityExceeded(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


_capacity: CsChatCapacity | None = None


def get_cs_capacity() -> CsChatCapacity:
    global _capacity
    if _capacity is None:
        s = get_settings()
        _capacity = CsChatCapacity(
            max_concurrent=s.cs_chat_max_concurrent,
            queue_timeout_sec=s.cs_chat_queue_timeout_sec,
            rate_per_minute_per_ip=s.cs_chat_rate_per_minute_per_ip,
        )
    return _capacity
