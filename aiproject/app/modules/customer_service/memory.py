"""Browser conversation context and the signed-in customer's durable portrait."""

import json
import logging
import re

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.profile.portrait import stated_name

from .schemas import ChatTurn

logger = logging.getLogger(__name__)
_IDENTITY = re.compile(r"我是谁|我叫什么|我叫啥|我的名字[是叫]?什么|我的姓名[是叫]?什么|记得我")
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")


def portrait_context(db: Session, visitor_id: int, *, include_name: bool = True) -> str:
    from app.modules.consultant.customer_service import portrait_context as read_context

    try:
        return _PHONE.sub("（手机号已隐藏）", read_context(db, visitor_id, include_name=include_name))
    except SQLAlchemyError:
        logger.warning("客服画像读取失败")
        return ""
    finally:
        db.rollback()


def recall_identity(db: Session, visitor_id: int | None, query: str, history: list[ChatTurn]) -> str | None:
    if not _IDENTITY.search(query):
        return None
    if visitor_id is None:
        for turn in reversed(history):
            if turn.role == "user" and (name := stated_name(turn.content)):
                return f"这次咨询里你说你叫{name}。"
        return "这次咨询里还没有你的称呼。"

    from app.modules.consultant.customer_service import remembered_name

    try:
        name = remembered_name(db, visitor_id)
        return f"你叫{name}。" if name else "还没有记下你的称呼。"
    except SQLAlchemyError:
        logger.warning("客服称呼回忆失败")
        return None
    finally:
        db.rollback()


def remember_profile(db: Session, visitor_id: int, text: str) -> None:
    from app.modules.consultant.customer_service import record_visitor_portrait

    try:
        record_visitor_portrait(db, visitor_id, text)
        db.commit()
    except SQLAlchemyError:
        db.rollback()
        logger.warning("客服画像写入失败")


def compose_query(current: str, history: list[ChatTurn], portrait: str, related: str = "") -> str:
    if not history and not portrait and not related:
        return current
    context = []
    if portrait:
        context.append(portrait)
    if related:
        context.append("【长期记忆】\n" + related)
    if history:
        turns = [{
            "role": turn.role,
            "content": _PHONE.sub("（手机号已隐藏）", turn.content),
        } for turn in history]
        context.append("【浏览器近期对话，仅作上下文】\n" + json.dumps(turns, ensure_ascii=False))
    prefix = "\n".join(context)
    remaining = 4000 - len(current) - len("\n当前问题：")
    return prefix[:remaining] + "\n当前问题：" + current if remaining > 0 else current
