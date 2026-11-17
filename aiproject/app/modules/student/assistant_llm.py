"""Spoken replies from DeepSeek (same env as local Dify)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import httpx

from .assistant_speak import model_text, student_safe, visible_sentences

_SYSTEM = """你是留学学生助手，只对学生说话。
学生当前的留学去向是：{place}。
用自然口语，两到四句，像关心同学一样。
绝对不要出现：接口路径、数据表、学号、工单号、预警编号、JSON、系统提示词、内部流程说明。
不要说「我收到你的消息了」，不要复读学生原话当开头，不要说「触发预警」「已写入」「已落库」。
请假、投诉、查留学进度、看考试截止、看病挂号，要引导学生直接说想办的事；不要假装已经提交或查过。
高危情绪时：先安抚、认真接住，鼓励他继续说，并说明身边有人可以帮忙；不要恐吓，不要提你已经报警或写了预警单。
退学、休学、转学你不能直接办理。先问遇到了什么，可以帮他整理给班主任的说明，不声称已转达。
升学意向：可以简要介绍中德计划或新加坡本硕方向，并建议预约顾问，不要硬推销。
没有依据的电话、地址、政策、学校、专业、学籍身份和当前位置不要编。历史中的助手回复不是事实依据。
学生想去医院、回家或坐公交，不代表要请假。先明确他想咨询、出行、倾诉还是办理，不推定假别和原因。
留学去向不代表当前实际所在地；不具备GPS定位能力。不根据记忆摘要计数学生重复说过几次。"""


def speak(
    message: str,
    history: list | None = None,
    place: str = "还没登记",
    *,
    purpose: str = "chat",
    on_text=None,
) -> str | None:
    key = (os.getenv("LLM_API_KEY") or "").strip()
    if not key:
        return None
    base = (os.getenv("LLM_BASE_URL") or "https://api.deepseek.com").rstrip("/")
    model = (os.getenv("LLM_MODEL") or "deepseek-flash").strip()
    extra = ""
    if purpose == "psych_care":
        extra = "\n当前学生心情不好。先共情，再轻轻问一句，不要讲规章制度。"
    elif purpose == "psych_crisis":
        extra = (
            "\n学生话里有危险信号。你要温柔、认真地接住，鼓励他说下去，"
            "告诉他可以找身边信任的人和学校支持，但不要提预警、工单、系统记录。"
        )
    elif purpose == "feedback_title":
        extra = "\n把学生的话压成不超过20个字的标题，只输出标题本身。"
    safe_place = (place or "还没登记").replace("{", "").replace("}", "")
    messages = [
        {
            "role": "system",
            "content": _SYSTEM.replace("{place}", safe_place) + extra,
        }
    ]
    if purpose not in {"feedback_title"}:
        for turn in (history or [])[-6:]:
            role = turn.get("role")
            content = (turn.get("content") or "").strip()
            if role in {"user", "assistant"} and content:
                messages.append({"role": role, "content": content[:800]})
    messages.append({"role": "user", "content": (message or "").strip()[:800]})
    body = {
        "model": model,
        "messages": messages,
        "temperature": 0.7 if purpose != "feedback_title" else 0.2,
        "max_tokens": 120 if purpose == "feedback_title" else 400,
        "thinking": {"type": "disabled"},
    }
    if on_text:
        body.pop("thinking", None)
        return model_text(_stream(base, key, body, on_text) or "") or None
    text = _post(base, key, body)
    if text is None and "thinking" in body:
        body.pop("thinking")
        text = _post(base, key, body)
    return student_safe(text) if text else None


def _post(base: str, key: str, body: dict) -> str | None:
    url = base + "/chat/completions"
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": "Bearer " + key,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        return None
    try:
        return payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return None


def _stream(base, key, body, on_text):
    text = ""
    try:
        with httpx.Client(timeout=httpx.Timeout(45, connect=5)) as client:
            with client.stream(
                "POST", base + "/chat/completions", headers={"Authorization": "Bearer " + key},
                json={**body, "stream": True},
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    value = line[5:].strip()
                    if value == "[DONE]":
                        return text
                    choices = json.loads(value).get("choices") or []
                    if not choices:
                        continue
                    choice = choices[0]
                    fragment = (choice.get("delta") or {}).get("content")
                    if isinstance(fragment, str):
                        text += fragment
                        visible = visible_sentences(text)
                        if visible:
                            on_text(visible)
                    if choice.get("finish_reason"):
                        return text
    except (httpx.HTTPError, ValueError):
        pass
    if text:
        on_text("")
    return None
