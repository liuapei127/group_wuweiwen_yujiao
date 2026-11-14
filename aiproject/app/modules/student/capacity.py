"""学生助手容量控制（进程内；多副本部署需在网关或 Redis 层限流）。

和客服 /api/cs/chat 分开计数，互不挤占。Dify 薄壳会回调
``/api/v1/student/assistant/run``，那一次调用已经在 ``/assistant`` 上占用过
槽位，因此内层只做频率检查（``rate_only``），不再排队等信号量，避免同进程
嵌套取槽把自己锁死。
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from app.core.config import get_settings
from app.modules.customer_service.capacity import CsCapacityExceeded, CsChatCapacity


class StuChatCapacity(CsChatCapacity):
    @asynccontextmanager
    async def rate_only(self, client_ip: str) -> AsyncIterator[None]:
        if not self._rate_ok(client_ip or "unknown"):
            raise CsCapacityExceeded("请求过于频繁，请稍后再试")
        yield


_capacity: StuChatCapacity | None = None


def get_stu_capacity() -> StuChatCapacity:
    global _capacity
    if _capacity is None:
        settings = get_settings()
        _capacity = StuChatCapacity(
            max_concurrent=settings.stu_chat_max_concurrent,
            queue_timeout_sec=settings.stu_chat_queue_timeout_sec,
            rate_per_minute_per_ip=settings.stu_chat_rate_per_minute_per_ip,
        )
    return _capacity
