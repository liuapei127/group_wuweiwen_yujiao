from typing import Literal

from fastapi import APIRouter, Query, Request

from app.core.responses import success
from app.core.responses.streaming import chat_response
from app.modules.visitor.router import Database, Principal

from .schemas import PublicChatRequest
from .service import catalog_for_dify, chat

router = APIRouter(prefix="/api/cs", tags=["官网客服"])


@router.post("/chat")
async def public_chat(body: PublicChatRequest, request: Request, db: Database):
    client_ip = request.client.host if request.client else "unknown"
    return await _reply(body, request, db, client_ip)


@router.post("/visitor/chat")
async def visitor_chat(body: PublicChatRequest, request: Request, db: Database, principal: Principal):
    client_ip = request.client.host if request.client else "unknown"
    return await _reply(body, request, db, client_ip, principal.visitor_id)


async def _reply(body, request, db, client_ip, visitor_id=None):
    async def run(on_text=None):
        answer = await chat(body, client_ip, db, visitor_id=visitor_id, on_text=on_text)
        return answer.model_dump(exclude_none=True, exclude_defaults=True)

    return chat_response(run) if "text/event-stream" in request.headers.get("accept", "") else success(await run())


@router.get("/catalog/{kind}")
def public_catalog(
    kind: Literal["recommendations", "activities"], db: Database,
    query: str = Query(min_length=1, max_length=4000),
):
    return success(catalog_for_dify(db, kind, query))
