"""Short-lived profile subscriptions on the existing authenticated read routes."""

import asyncio
import time

from starlette.concurrency import run_in_threadpool

from app.core.responses.streaming import chat_response


def watch_profile(db, get_version, known_version):
    db.rollback()

    def check():
        try:
            return get_version()
        finally:
            db.rollback()

    async def read_update(_):
        deadline = time.monotonic() + 12
        while True:
            version = await run_in_threadpool(check)
            if version != known_version or time.monotonic() >= deadline:
                return {"changed": version != known_version}
            await asyncio.sleep(0.75)

    return chat_response(read_update)
