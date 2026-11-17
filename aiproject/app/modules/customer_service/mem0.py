"""Publish and retrieve current customer portrait facts through Mem0."""

import asyncio
import hashlib
import logging
from functools import lru_cache

import httpx
from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)
_ROOT = "https://api.mem0.ai/v3/memories/"
_APP = "yujiao-customer-service"


class _Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    cs_mem0_api_key: SecretStr = SecretStr("")


@lru_cache
def _api_key() -> str:
    return _Settings().cs_mem0_api_key.get_secret_value().strip()


def configured() -> bool:
    return bool(_api_key())


async def current_memory(visitor_id: int, portrait: str, query: str) -> str:
    return await _memory(visitor_id, portrait, query) or ""


async def sync_profile(bind, visitor_id: int) -> None:
    if not configured():
        return

    from .memory import portrait_context

    def read():
        with Session(bind) as db:
            return portrait_context(db, visitor_id, include_name=False)

    for attempt in range(2):
        portrait = await run_in_threadpool(read)
        if not portrait or await _memory(visitor_id, portrait, "留学咨询画像") is not None:
            return
        if attempt == 0:
            await asyncio.sleep(1)


async def _memory(visitor_id: int, portrait: str, query: str) -> str | None:
    key = _api_key()
    if not key or not portrait:
        return ""
    facts = [line[2:] for line in portrait.splitlines() if line.startswith("- ")]
    if not facts:
        return ""
    fingerprint = hashlib.sha256(portrait.encode()).hexdigest()
    user = f"{_APP}:{visitor_id}"
    try:
        async with httpx.AsyncClient(timeout=2.0, trust_env=False, headers={"Authorization": f"Token {key}"}) as client:
            response = await client.post(_ROOT + "search/", json={
                "query": query, "filters": {"user_id": user, "app_id": _APP},
                "metadata": {"portrait": fingerprint}, "top_k": len(facts), "threshold": 0,
            })
            response.raise_for_status()
            rows = response.json().get("results", [])
            if not isinstance(rows, list):
                return ""
            retrieved = list(dict.fromkeys(
                row["memory"] for row in rows if isinstance(row, dict)
                and row.get("user_id", user) == user
                and (row.get("metadata") or {}).get("portrait") == fingerprint
                and row.get("memory") in facts
            ))
            if not retrieved:
                response = await client.post(_ROOT + "add/", json={
                    "messages": [{"role": "user", "content": fact} for fact in facts],
                    "user_id": user, "app_id": _APP, "infer": False,
                    "metadata": {"portrait": fingerprint},
                })
                response.raise_for_status()
            return "\n".join(retrieved[:3])
    except (httpx.HTTPError, ValueError, AttributeError, TypeError):
        logger.warning("客服 Mem0 同步暂不可用")
        return None
