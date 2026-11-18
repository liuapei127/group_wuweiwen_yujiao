"""Browser conversation context and the signed-in customer's durable portrait."""

import json
import logging
import re

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.modules.profile.portrait import person_updates, stated_name

from .schemas import ChatTurn

logger = logging.getLogger(__name__)
_IDENTITY = re.compile(r"我是谁|我叫什么|我叫啥|我的名字[是叫]?什么|我的姓名[是叫]?什么|记得我")
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_AGE_QUESTION = re.compile(
    r"(?:你(?:还)?(?:知道|记得)|请问|请告诉我)?"
    r"(?:我(?:今年|现在)?(?:几岁|多少岁|多大(?:年龄)?)|我的年龄(?:是)?多少)(?:了)?(?:吗|呢)?"
)


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
    asks_age = _AGE_QUESTION.fullmatch(re.sub(r'[\s？?。！!，,]', '', query)) is not None
    if not asks_age and not _IDENTITY.search(query):
        return None
    if visitor_id is None:
        if asks_age:
            for turn in reversed(history):
                if turn.role == 'user' and (age := person_updates(turn.content).get('age')) is not None:
                    return f'这次咨询里你说你{age}岁。'
            return '这次咨询里还没有记下你的年龄，你今年多少岁？'
        for turn in reversed(history):
            if turn.role == "user" and (name := stated_name(turn.content)):
                return f"这次咨询里你说你叫{name}。"
        return "这次咨询里还没有你的称呼。"

    from app.modules.consultant.customer_service import remembered_age, remembered_name

    try:
        if asks_age:
            age = remembered_age(db, visitor_id)
            return f'资料中记录你{age}岁。' if age is not None else '你的资料中还没有记录年龄，你今年多少岁？'
        name = remembered_name(db, visitor_id)
        return f"你叫{name}。" if name else "还没有记下你的称呼。"
    except SQLAlchemyError:
        logger.warning("客服个人资料回忆失败")
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
    suffix = "\n当前问题：" + current
    remaining = 4000 - len(suffix)
    if remaining <= 0:
        return current
    recent = ''
    if history:
        header = '【浏览器近期对话，仅作上下文】\n'
        budget = remaining // 2 if portrait or related else remaining
        turns = []
        for turn in reversed(history):
            candidate = [{'role': turn.role, 'content': _PHONE.sub('（手机号已隐藏）', turn.content)}, *turns]
            serialized = header + json.dumps(candidate, ensure_ascii=False)
            if len(serialized) > budget:
                break
            turns = candidate
            recent = serialized
    context = []
    if portrait:
        context.append(portrait)
    if related:
        context.append("【长期记忆】\n" + related)
    profile_budget = remaining - len(recent) - (1 if recent else 0)
    prefix = '\n'.join(context)[:max(0, profile_budget)]
    return '\n'.join(part for part in (prefix, recent) if part) + suffix
