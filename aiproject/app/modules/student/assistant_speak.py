"""Keep student-facing sentences free of internal ids and API paths."""

import re

_LEAK = re.compile(
    r"(工单号?\s*[#＃]?\s*\d+"
    r"|alert\s*[#＃]?\s*\d+"
    r"|请假\s*[#＃]?\s*\d+"
    r"|学生\s*[#＃]?\s*\d+"
    r"|record_id\s*[#＃:=]?\s*\d+"
    r"|POST\s+/api/\S+"
    r"|GET\s+/api/\S+"
    r"|/api/stu/\S+"
    r"|/api/v1/student\S*"
    r"|[#＃]\d+)",
    re.IGNORECASE,
)


def student_safe(text: str) -> str:
    cleaned = _LEAK.sub("", text or "")
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def feedback_summary(detail: str) -> str:
    text = re.sub(r"\s+", " ", (detail or "").strip())
    if not text:
        return "学生反映的问题"
    if len(text) <= 48:
        return text
    return text[:45].rstrip("，,。；; ") + "…"


def model_text(text: str) -> str:
    for marker in ("</think>", "<｜end▁of▁thinking｜>"):
        if marker in text:
            text = text.rsplit(marker, 1)[1]
    if "<think" in text or "<!--dify" in text or text.lstrip().startswith("<"):
        return ""
    return student_safe(text)


def visible_sentences(text: str) -> str:
    # Leave the last incomplete sentence buffered so split internal identifiers are removed.
    boundary = max((m.end() for m in re.finditer(r"[。！？\n]", text)), default=0)
    return model_text(text[:boundary]) if boundary else ""
