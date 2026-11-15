import logging
import re
from secrets import token_hex

import httpx
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.core.security.credentials import utc_now
from app.modules.events import service as events
from app.modules.profile import service as profile
from app.modules.visitor.catalog import list_courses

from .booking import booking_reply
from .capacity import CsCapacityExceeded, get_cs_capacity
from .catalog import activity_list, country_for, names_event, recommendations
from .repository import chat_session, remember_dify_conversation
from .schemas import PublicChatReply, PublicChatRequest

logger = logging.getLogger(__name__)
_FALLBACK = "在线咨询暂时不可用。请查看官网服务指引，或登录后联系顾问。"
_MATERIALS = ("材料", "资料", "上传")
_POLICY = ("签证", "准证", "政策")
_FLOW_FAILURE = ("run failed", "request failed with status code", "traceback", "plugininvokeerror")
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")


async def chat(
    body: PublicChatRequest, client_ip: str, db: Session, *, visitor_id: int | None = None,
) -> PublicChatReply:
    try:
        async with get_cs_capacity().slot(client_ip):
            return await _chat(body, db, visitor_id)
    except CsCapacityExceeded as exc:
        raise BusinessError(429, exc.message) from exc


async def _chat(body: PublicChatRequest, db: Session, visitor_id: int | None) -> PublicChatReply:
    settings = get_settings()
    key = settings.cs_public_dify_api_key.get_secret_value().strip()
    query = _PHONE.sub("（手机号已隐藏）", body.query)
    session_id = None
    conversation_id = None
    expanded = query
    if body.start_session or body.session_id:
        session_id, conversation_id, expanded, local = await run_in_threadpool(
            _session_turn, db, body.session_id, visitor_id, query
        )
        if local is not None:
            return local
    elif visitor_id is not None:
        local = await run_in_threadpool(_legacy_visitor_answer, db, visitor_id, query)
        if local is not None:
            return local
        await run_in_threadpool(db.rollback)

    if not key and session_id is None:
        raise BusinessError(503, "咨询助手暂未配置")
    try:
        if not key:
            raise BusinessError(503, "咨询助手暂未配置")
        answer, next_conversation = await _request_answer(
            expanded, key, settings.dify_api_url, settings.dify_timeout_seconds,
            user=session_id or f"guest_{token_hex(16)}", conversation_id=conversation_id,
        )
    except BusinessError:
        if session_id is None:
            raise
        return PublicChatReply(answer=_FALLBACK, session_id=session_id)

    if session_id and next_conversation and next_conversation != conversation_id:
        try:
            await run_in_threadpool(
                remember_dify_conversation, db, session_id, visitor_id,
                utc_now(), conversation_id, next_conversation,
            )
        except (BusinessError, SQLAlchemyError):
            await run_in_threadpool(db.rollback)
            logger.warning("客服回复已生成，但会话续接状态未保存")
    return PublicChatReply(answer=answer, session_id=session_id)


def _session_turn(db: Session, session_id: str | None, visitor_id: int | None, query: str):
    state = chat_session(db, session_id, visitor_id, utc_now())
    previous = state.previous_query or ""
    expanded = query
    country = country_for(query)
    if country and not names_event(query) and not names_event(previous) and re.search(r"^(?:改成|换成|换个|改去|想去|换去|去)?(?:德国|新加坡)[呢吧？?。！! ]*$", query):
        if any(word in previous for word in ("推荐", "适合", "学历")):
            old_country = country_for(previous)
            expanded = previous.replace(old_country, country) if old_country else f"{country}：{previous}"
    if any(word in previous for word in _POLICY):
        if country and len(query) <= 10:
            expanded = f"{country}留学政策。此前的问题：{previous}"
        elif query in ("那需要什么材料", "需要什么材料", "要多久", "需要多久", "怎么办"):
            expanded = f"{previous}。接着问：{query}"
    local = _account_answer(db, visitor_id, expanded)
    if local is None:
        local = booking_reply(db, state, query)
    state.previous_query = expanded[:1200]
    current_id, conversation_id = state.id, state.dify_conversation_id
    if local is not None:
        local.session_id = current_id
    db.commit()
    return current_id, conversation_id, expanded[:4000], local


def _account_answer(db: Session, visitor_id: int | None, query: str) -> PublicChatReply | None:
    if not any(word in query for word in _MATERIALS) or any(word in query for word in _POLICY):
        return None
    if any(word in query for word in ("进度", "状态", "已交", "通过", "查", "我的")):
        if visitor_id is None:
            return PublicChatReply(answer="请登录官网，在「材料提交」查看本账号的材料记录。")
        statuses = {"received": "已收到", "needs_information": "待补充", "reviewed": "已研判"}
        rows = profile.visitor_materials(db, visitor_id, None, 5)
        lines = [f"{row.file_name or '文字材料'}：{statuses.get(row.status, row.status)}" for row in rows]
        return PublicChatReply(answer="最近的材料记录：\n" + "\n".join(lines) if lines else "当前账号还没有材料提交记录。")
    return PublicChatReply(answer="可先在官网「材料提交」上传已有文件或填写文字说明。提交后由顾问核对；缺少的材料可以等顾问联系后补录。")


def _legacy_visitor_answer(db: Session, visitor_id: int, query: str) -> PublicChatReply | None:
    local = _account_answer(db, visitor_id, query)
    if local is not None:
        return local
    if names_event(query) or "预约" in query:
        if any(word in query for word in ("我的", "已约", "预约记录", "预约状态")):
            statuses = {"registered": "已预约", "cancelled": "已取消", "attended": "已签到", "no_show": "未到场"}
            rows = events.visitor_reservations(db, visitor_id, None, 5)
            lines = [f"{row.event.event_name}：{statuses[row.reservation.status]}" for row in rows]
            return PublicChatReply(answer="最近的预约记录：\n" + "\n".join(lines) if lines else "当前账号还没有活动预约记录。")
        if any(word in query for word in ("怎样", "怎么", "如何", "取消")):
            return PublicChatReply(answer="打开「活动预约」选择有名额的场次。已预约的场次可以在「我的预约」取消。")
        rows = events.upcoming_events(db, visitor_id, 0, 5)
        lines = [f"{row.event_name}，{row.start_time:%m月%d日 %H:%M}" for row in rows]
        return PublicChatReply(answer="近期活动（北京时间）：\n" + "\n".join(lines) if lines else "暂时没有开放预约的活动。")
    if any(word in query for word in ("课程", "项目", "价格", "学费")):
        keyword = next((word for word in ("新加坡", "德国", "航空", "酒店", "双元制") if word in query), "")
        rows = list_courses(db, keyword, 0, 5).items
        lines = [f"{row.project_name}" + (f"（¥{row.price}）" if row.price is not None else "") for row in rows]
        if lines:
            return PublicChatReply(answer="目前上架的课程与项目：\n" + "\n".join(lines) + "\n更多详情请打开「课程与项目」。")
        return PublicChatReply(answer="暂无匹配的上架课程。可在「课程与项目」搜索，或向顾问咨询。")
    if any(word in query for word in _POLICY):
        return PublicChatReply(answer="请打开「留学政策」，选择新加坡或德国查看官网收录的官方办理入口。")
    return None


async def _request_answer(
    query: str, key: str, api_url: str, timeout: int, *, user: str, conversation_id: str | None,
) -> tuple[str, str | None]:
    payload = {"inputs": {}, "query": query, "user": user, "response_mode": "blocking"}
    if conversation_id:
        payload["conversation_id"] = conversation_id
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(timeout, connect=5)) as client:
            response = await client.post(
                api_url.rstrip("/") + "/chat-messages", headers={"Authorization": "Bearer " + key}, json=payload,
            )
            if response.status_code == 404 and conversation_id:
                payload.pop("conversation_id")
                response = await client.post(
                    api_url.rstrip("/") + "/chat-messages", headers={"Authorization": "Bearer " + key}, json=payload,
                )
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise BusinessError(502, "咨询助手暂不可用，请稍后重试") from exc

    answer = result.get("answer") if isinstance(result, dict) else None
    if not isinstance(answer, str) or not answer.strip() or any(marker in answer[:180].lower() for marker in _FLOW_FAILURE):
        raise BusinessError(502, "咨询助手未返回有效答复")
    next_id = result.get("conversation_id")
    return answer.strip(), next_id if isinstance(next_id, str) and 0 < len(next_id) <= 64 else None


def catalog_for_dify(db: Session, kind: str, query: str) -> list[dict]:
    return recommendations(db, query) if kind == "recommendations" else activity_list(db, query)
