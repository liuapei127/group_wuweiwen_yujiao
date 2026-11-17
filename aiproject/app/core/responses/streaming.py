"""Server-Sent Events for chat replies and confirmed turn results."""
import asyncio
from contextlib import suppress
import json
import logging

from anyio import CancelScope
from fastapi.encoders import jsonable_encoder
from fastapi.responses import StreamingResponse

from app.core.exceptions import BusinessError

logger = logging.getLogger(__name__)


def _frame(event, payload):
    data = json.dumps(jsonable_encoder(payload), ensure_ascii=False)
    return f"event: {event}\ndata: {data}\n\n"


def chat_response(run):
    async def events():
        changed = asyncio.Event()
        loop = asyncio.get_running_loop()
        visible = ""
        outcome = None

        def save_text(text):
            nonlocal visible
            visible = text
            changed.set()

        def publish(text):
            loop.call_soon_threadsafe(save_text, text)

        async def produce():
            nonlocal outcome
            try:
                result = await run(publish)
                outcome = ("result", {"data": result})
            except BusinessError as exc:
                outcome = ("error", {"status": exc.status_code, "message": exc.detail})
            except Exception:
                logger.exception("Chat stream failed")
                outcome = ("error", {"status": 500, "message": "回复中断，请先查看记录后再试。"})
            finally:
                changed.set()

        task = asyncio.create_task(produce())
        sent = ""
        try:
            yield ": connected\n\n"
            while True:
                try:
                    await asyncio.wait_for(changed.wait(), timeout=12)
                except TimeoutError:
                    yield ": keepalive\n\n"
                    continue
                changed.clear()
                if visible != sent:
                    sent = visible
                    yield _frame("text", {"text": sent})
                if outcome is not None:
                    yield _frame(*outcome)
                    break
        finally:
            # A turn may already have submitted a business operation when the tab closes.
            with CancelScope(shield=True), suppress(asyncio.CancelledError):
                await task

    return StreamingResponse(events(), media_type="text/event-stream", headers={
        "Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no",
    })
