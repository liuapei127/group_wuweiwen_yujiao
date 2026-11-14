"""Shared safety vocabulary for the student assistant.

Keep the crisis list in one place: intent routing, the local brain and the
psych-alert writer must agree on what counts as an immediate risk.
"""

from __future__ import annotations

HIGH_RISK_TERMS = (
    "自杀",
    "自尽",
    "轻生",
    "不想活",
    "不想活了",
    "活不下去",
    "结束生命",
    "结束自己",
    "伤害自己",
    "自残",
    "割腕",
    "跳楼",
    "想死",
    "死了算了",
    "不如死",
    "活着没意思",
    "活着没意义",
    "一了百了",
)

PSYCH_CARE_TERMS = (
    "心情",
    "情绪",
    "想家",
    "绝望",
    "压力大",
    "难受",
    "不开心",
    "焦虑",
    "失眠",
    "孤单",
    "害怕",
)


def high_risk_hits(text: str) -> list[str]:
    """Return matched crisis terms without duplicates, preserving list order."""
    value = text or ""
    return [term for term in HIGH_RISK_TERMS if term in value]
