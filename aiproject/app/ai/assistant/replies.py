"""Render business responses for the employee assistant."""
import json
import re

from app.ai.workflows.ent_contracts import format_result
from .query_results import query_result

_GREETING_MESSAGES = {"你好", "您好", "早上好", "中午好", "下午好", "晚上好", "嗨", "hi", "hello", "hey"}
_TEST_MESSAGES = {"test", "测试", "测试一下", "ping", "在吗"}
_CAPABILITIES_QUESTION = re.compile(
    r"(?:请问)?(?:你|您|ent\s*助手)?(?:都|主要)?"
    r"(?:有(?:哪些|什么)功能|能(?:帮我)?做什么|能干什么|会做什么|会干嘛|能帮我什么|是谁|介绍一下自己)"
    r"(?:吗|呢|呀|啊)?"
)
_READ_FEATURES = {
    "crm:read": "客户与跟进",
    "reports:read": "本人日报",
    "reports:summary:read": "授权范围内的日报汇总",
    "directory:read": "组织与同事",
    "guides:read": "新人指南",
    "scores:read": "学生成绩",
    "leaves:read": "请假单",
    "tickets:read": "工单",
    "todos:read": "待办",
    "notifications:read": "通知",
}
_WRITE_FEATURES = {
    "crm:write", "reports:write", "guides:write", "scores:write", "leaves:approve",
    "tickets:write", "todos:write", "reports:formal:generate",
}
_LEGACY_PREFIX = "后端查询结果（仅来自实际响应）：\n"
_DISPLAY_LIMIT = 30
_CONFIRMATION_NAMES = {
    'todo_create':'新增待办','todo_update':'更新待办','lead_create':'录入客户','lead_update':'修改客户',
    'lead_status':'更新客户状态','lead_follow_up':'追加客户跟进','daily_submit':'提交日报',
    'formal_report':'生成并归档正式报告','guide_create':'新增指南','score_create':'录入成绩',
    'score_correct':'更正成绩','leave_approve':'审批请假','ticket_update':'处理工单',
}
_LEAD_STATUS_LABELS = {
    "new": "新线索",
    "contacting": "联系中",
    "qualified": "已确认意向",
    "signed": "已签约",
    "lost": "已流失",
}


def conversational_reply(text, permissions=frozenset()):
    normalized = text.casefold().strip(" \t\r\n。！!?？.")
    if normalized in _GREETING_MESSAGES:
        return "你好，我是 ENT 助手。你想查询什么，或办理什么事项？"
    if normalized in _TEST_MESSAGES:
        return "消息已收到。你可以直接告诉我想查询或办理的事项。"
    if _CAPABILITIES_QUESTION.fullmatch(normalized):
        answer = "我是 ENT 助手，可以和你聊聊，也能帮你查工作资料。"
        available = [label for permission, label in _READ_FEATURES.items() if permission in permissions]
        if available:
            answer += "\n你当前可以查询" + "、".join(available) + "。"
        if _WRITE_FEATURES.intersection(permissions):
            answer += "\n涉及提交、修改或审批，我会先请你确认。"
        return answer
    return None


def chat_history(messages):
    turns = []
    for question, answer in zip(messages, messages[1:]):
        if (question["role"] == "user" and answer["role"] == "assistant"
                and answer["metadata"].get("mode") == "chat"):
            turns.append({"user": question["content"][:400], "assistant": answer["content"][:400]})
    return json.dumps(turns[-3:], ensure_ascii=False) if turns else ""


def _organizations(rows):
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or not isinstance(row.get("org_name"), str) or not isinstance(row.get("id"), int)
        for row in rows
    ):
        return "组织架构查询返回的格式有误，请稍后重试。"
    if not rows:
        return "没有查到符合条件的组织。"

    ids = {row["id"] for row in rows}
    children = {}
    for row in rows:
        parent = row.get("parent_id")
        children.setdefault(parent if isinstance(parent, int) and parent in ids else None, []).append(row)

    lines = []
    seen = set()

    def append_branch(row, depth):
        org_id = row["id"]
        if org_id in seen or len(lines) >= _DISPLAY_LIMIT:
            return
        seen.add(org_id)
        prefix = "  " * min(depth, 8) + ("└ " if depth else "• ")
        lines.append(prefix + row["org_name"])
        for child in children.get(org_id, ()):
            append_branch(child, depth + 1)

    for row in children.get(None, ()):
        append_branch(row, 0)
    for row in rows:
        append_branch(row, 0)

    if len(rows) > len(lines):
        lines.append(f"这里只显示前 {len(lines)} 个，可按组织名称缩小范围。")
    if any(row["org_name"].startswith("ENT_LOCAL_VERIFY_V1_") for row in rows):
        lines.append("带 ENT_LOCAL_VERIFY_V1 标记的是本地联调组织。")
    return f"查到 {len(rows)} 个组织：\n" + "\n".join(lines)


def _customer_list(result):
    rows = result.get("items") if isinstance(result, dict) else None
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or not isinstance(row.get("customer_name"), str) or not isinstance(row.get("id"), int)
        for row in rows
    ):
        return "客户列表查询返回的格式有误，请稍后重试。"

    total = result.get("total")
    if not isinstance(total, int):
        total = len(rows)
    if not rows:
        return "这一页没有客户记录。" if total else "没有查到符合条件的客户。"

    lines = []
    for row in rows[:_DISPLAY_LIMIT]:
        status = _LEAD_STATUS_LABELS.get(row.get("status"), "状态未提供")
        line = f"• {row['customer_name']}（编号 {row['id']}） · {status}"
        if row.get("intended_country"):
            line += f" · 意向 {row['intended_country']}"
        lines.append(line)
    if len(lines) < total:
        lines.append(f"当前显示 {len(lines)} 位，可按姓名缩小范围或到「客户管理」查看完整列表。")
    return f"查到 {total} 位客户：\n" + "\n".join(lines)


def _scores(rows):
    if not isinstance(rows, list) or any(
        not isinstance(row, dict) or not isinstance(row.get("course_name"), str) or row.get("score") is None
        for row in rows
    ):
        return "成绩查询返回的格式有误，请稍后重试。"
    if not rows:
        return "没有查到这名学生的成绩记录。"

    lines = []
    for row in rows[:_DISPLAY_LIMIT]:
        fields = [row["course_name"], f"{row['score']} 分"]
        if row.get("semester"):
            fields.append(str(row["semester"]))
        if row.get("id"):
            fields.append(f"成绩编号 {row['id']}")
        if row.get("version"):
            fields.append(f"版本 {row['version']}")
        lines.append("• " + " · ".join(fields))
    if len(rows) > len(lines):
        lines.append(f"当前显示前 {len(lines)} 条，可按学期缩小查询范围。")
    return f"查到 {len(rows)} 条成绩记录：\n" + "\n".join(lines)


_QUERY_FORMATTERS = {"organizations": _organizations, "lead_list": _customer_list, "scores": _scores}


def business_reply(status, body, intent):
    if status == 200:
        try:
            payload = json.loads(body)
        except (TypeError, ValueError):
            payload = None
        if isinstance(payload, dict) and payload.get("code") == 0:
            if intent in _QUERY_FORMATTERS:
                return _QUERY_FORMATTERS[intent](payload.get("data"))
            rendered = query_result(intent, payload.get("data"))
            if rendered is not None:
                return rendered
    return format_result(status, body, intent)["reply"]


def display_stored_reply(message):
    content = message["content"]
    intent = message["metadata"].get("action")
    if (message['role']=='assistant' and content.startswith('请核对以下操作')
            and intent in _CONFIRMATION_NAMES and not message['metadata'].get('executed')):
        return '已整理“'+_CONFIRMATION_NAMES[intent]+'”的信息，请核对下方内容。确认后才会提交，也可以取消。'
    if message["role"] != "assistant" or not content.startswith(_LEGACY_PREFIX):
        return content
    try:
        result = json.loads(content.removeprefix(_LEGACY_PREFIX))
    except ValueError:
        return "这条历史查询结果过长，请重新查询以查看明细。"
    if intent in _QUERY_FORMATTERS:
        return _QUERY_FORMATTERS[intent](result)
    return query_result(intent, result) or content


def saved_reply(conversation):
    messages = conversation.get('messages', [])
    if messages and messages[-1].get('role') == 'assistant':
        return messages[-1].get('content', '')
    return ''
