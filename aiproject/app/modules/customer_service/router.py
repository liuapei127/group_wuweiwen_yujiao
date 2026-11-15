from typing import Literal

from fastapi import APIRouter, Query, Request

from app.core.responses import success
from app.modules.visitor.router import Database, Principal

from .schemas import PublicChatRequest
from .service import catalog_for_dify, chat

router = APIRouter(prefix="/api/cs", tags=["官网客服"])


@router.post("/chat")
async def public_chat(body: PublicChatRequest, request: Request, db: Database):
    client_ip = request.client.host if request.client else "unknown"
    answer = await chat(body, client_ip, db)
    return success(answer.model_dump(exclude_none=True, exclude_defaults=True))


@router.post("/visitor/chat")
async def visitor_chat(body: PublicChatRequest, request: Request, db: Database, principal: Principal):
    client_ip = request.client.host if request.client else "unknown"
    answer = await chat(body, client_ip, db, visitor_id=principal.visitor_id)
    return success(answer.model_dump(exclude_none=True, exclude_defaults=True))


@router.get("/catalog/{kind}")
def public_catalog(
    kind: Literal["recommendations", "activities"], db: Database,
    query: str = Query(min_length=1, max_length=4000),
):
    return success(catalog_for_dify(db, kind, query))
