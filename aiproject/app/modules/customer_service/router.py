from fastapi import APIRouter, Request
from fastapi.concurrency import run_in_threadpool

from app.core.responses import success

from .schemas import PublicChatRequest
from app.modules.visitor.router import Database, Principal

from .service import chat, visitor_answer

router = APIRouter(prefix="/api/cs", tags=["官网客服"])


@router.post("/chat")
async def public_chat(body: PublicChatRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    return success(await chat(body.query, client_ip))


@router.post("/visitor/chat")
async def visitor_chat(body: PublicChatRequest, request: Request, db: Database, principal: Principal):
    answer = await run_in_threadpool(visitor_answer, db, principal.visitor_id, body.query)
    if answer is None:
        await run_in_threadpool(db.rollback)
        client_ip = request.client.host if request.client else "unknown"
        answer = await chat(body.query, client_ip)
    return success(answer)
