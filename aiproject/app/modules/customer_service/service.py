from secrets import token_hex

import httpx

from app.core.config import get_settings
from app.modules.events import service as events
from app.modules.profile import service as profile
from app.modules.visitor.catalog import list_courses
from app.core.exceptions import BusinessError

from .capacity import CsCapacityExceeded, get_cs_capacity
from .schemas import PublicChatReply


async def chat(query: str, client_ip: str, *, student: bool = False) -> PublicChatReply:
    settings = get_settings()
    key = (settings.stu_dify_api_key if student else settings.cs_public_dify_api_key).get_secret_value()
    if not key:
        raise BusinessError(503, "咨询助手暂未配置")

    capacity = get_cs_capacity()
    try:
        async with capacity.slot(client_ip):
            return await _request_answer(query, key, settings.dify_api_url, settings.dify_timeout_seconds)
    except CsCapacityExceeded as exc:
        raise BusinessError(429, exc.message) from exc


async def _request_answer(query: str, key: str, api_url: str, timeout: int) -> PublicChatReply:
    payload = {
        "inputs": {},
        "query": query,
        "user": f"guest_{token_hex(16)}",
        "response_mode": "blocking",
    }
    try:
        async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(timeout, connect=5)) as client:
            response = await client.post(
                api_url.rstrip("/") + "/chat-messages",
                headers={"Authorization": "Bearer " + key},
                json=payload,
            )
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise BusinessError(502, "咨询助手暂不可用，请稍后重试") from exc

    answer = result.get("answer") if isinstance(result, dict) else None
    if not isinstance(answer, str) or not answer.strip():
        raise BusinessError(502, "咨询助手未返回有效答复")
    return PublicChatReply(answer=answer)


def visitor_answer(db, visitor_id: int, query: str) -> PublicChatReply | None:
    """Answer account-specific questions locally using the authenticated visitor."""
    if any(word in query for word in ("材料", "资料", "上传")):
        if any(word in query for word in ("进度", "状态", "已交", "通过", "查", "我的")):
            statuses = {"received": "已收到", "needs_information": "待补充", "reviewed": "已研判"}
            rows = profile.visitor_materials(db, visitor_id, None, 5)
            lines = [f"{row.file_name or '文字材料'}：{statuses[row.status]}" for row in rows]
            return PublicChatReply(answer="最近的材料记录：\n" + "\n".join(lines) if lines else "当前账号还没有材料提交记录。")
        return PublicChatReply(answer="请在「材料提交」查看项目准备说明。你可以先提交已有的文件或文字，顾问联系后可以补录。")

    if any(word in query for word in ("预约", "讲座", "活动")):
        if any(word in query for word in ("我的", "已约", "预约记录", "预约状态")):
            statuses = {"registered": "已预约", "cancelled": "已取消", "attended": "已签到"}
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
    if any(word in query for word in ("政策", "签证", "准证")):
        return PublicChatReply(answer="请打开「留学政策」，选择新加坡或德国查看官网收录的官方办理入口。")
    return None
