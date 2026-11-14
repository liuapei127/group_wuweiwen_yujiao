"""Shared crisis vocabulary and leave state machine regressions."""

from datetime import datetime, timedelta

from app.modules.student import assistant_chat as chat
from app.modules.student.assistant_intent import route
from app.modules.student.assistant_safety import HIGH_RISK_TERMS, high_risk_hits


def test_high_risk_vocabulary_is_shared_with_intent_router():
    for phrase in ("我想跳楼", "我想死", "活着没意思", "不如死了算了"):
        assert high_risk_hits(phrase), phrase
        assert route(phrase)["intent"] == "psych", phrase
    # Harm phrases win over leave keywords so the alert is never skipped.
    assert route("我不想活了，想请假")["intent"] == "psych"


def test_soft_mood_words_do_not_outrank_business_intents():
    assert route("心情不好，想请假")["intent"] == "leave_create"
    assert route("最近焦虑，查进度")["intent"] == "progress"
    assert route("我有点想家")["intent"] == "psych"


def test_ack_and_stopwords_are_not_leave_reasons():
    assert chat._heard_reason("谢谢") == ""
    assert chat._heard_reason("好的") == ""
    assert chat._heard_reason("我要请假") == ""
    assert chat._heard_reason("病假 11月20号到21号，家里有事") == "家里有事"


def test_leave_slot_closes_after_success():
    history = [
        {"role": "user", "content": "我要请假。病假，2026-11-17 到 2026-11-19，身体不适。"},
        {"role": "assistant", "content": "已经帮你交上病假了，从2026-11-17 09:00到2026-11-19 18:00。"},
    ]
    assert chat._leave_pending(history) is False
    assert chat._follow_choice("谢谢", history) == (None, "谢谢")


def test_duplicate_leave_prompt_keeps_slot_open():
    history = [
        {"role": "user", "content": "我想请假 肚子疼"},
        {"role": "assistant", "content": "今天已提交过相同时间段的请假。换一组日期再说一次。"},
    ]
    assert chat._leave_pending(history) is True


def test_new_leave_is_not_polluted_by_previous_request():
    history = [
        {"role": "user", "content": "我要请假。病假，2026-11-17 到 2026-11-19，身体不适。"},
        {"role": "assistant", "content": "已经帮你交上病假了，从2026-11-17 09:00到2026-11-19 18:00。"},
    ]
    spoken = chat._compose_leave_utterance("我要请 12-01 到 12-02 的事假，家里有事", history)
    assert "11-17" not in spoken and "身体不适" not in spoken
    filled = chat._natural_leave(spoken, history)
    assert filled is not None
    assert filled["leave_type"] == "personal"
    assert (filled["start_time"].month, filled["start_time"].day) == (12, 1)
    assert filled["reason"] == "家里有事"


def test_multi_turn_slot_filling_keeps_earlier_answers():
    history = [
        {"role": "user", "content": "我要请假"},
        {"role": "assistant", "content": "可以请假。先告诉我是病假、事假还是紧急，顺便说从哪天到哪天、因为什么。"},
        {"role": "user", "content": "病假 11月20号到21号"},
        {"role": "assistant", "content": "好，先按病假。请再补充：事由。"},
    ]
    spoken = chat._compose_leave_utterance("家里有事", history)
    filled = chat._natural_leave(spoken, history)
    assert filled is not None
    assert filled["leave_type"] == "sick"
    assert (filled["start_time"].month, filled["start_time"].day) == (11, 20)
    assert filled["reason"] == "家里有事"


def test_cancel_leaves_the_slot():
    history = [{"role": "assistant", "content": "好，先按病假。请再补充：事由。"}]
    assert chat._is_cancel("算了")
    assert chat._follow_choice("算了", history) == (None, "算了")


def test_date_parsing_rolls_forward_and_handles_relative_days():
    today = chat.now_naive().date()
    start, end = chat._parse_leave_span("后天")
    assert start is not None and end is not None
    assert start.date() == today + timedelta(days=2)
    assert (start.hour, end.hour) == (9, 18)

    start, end = chat._parse_leave_span("明天下午2点到6点")
    assert (start.date(), start.hour, end.hour) == (today + timedelta(days=1), 14, 18)

    start, end = chat._parse_leave_span("12-01 到 12-02")
    assert start >= datetime.combine(today, datetime.min.time())
    assert (start.month, start.day, end.month, end.day) == (12, 1, 12, 2)

    # Bare day-of-month ranges move to the next month instead of the past.
    start, end = chat._parse_leave_span("3号到4号")
    assert start > datetime.combine(today, datetime.min.time())
    assert end > start


def test_month_day_far_in_the_past_is_not_pushed_a_year_forward():
    today = chat.now_naive().date()
    start, end = chat._parse_leave_span("11-01 到 11-02")
    assert start is not None and end is not None
    # 2027-11-01 would be a whole year away; keep the past date so it is rejected.
    assert start.date() < today
    assert (start.year, end.year) == (today.year, today.year)


def test_explicit_year_range_is_respected():
    start, end = chat._parse_leave_span("2026-12-25T08:30:00 到 2027-01-03T17:00:00")
    assert (start.year, start.month, start.day, start.hour) == (2026, 12, 25, 8)
    assert (end.year, end.month, end.day, end.hour) == (2027, 1, 3, 17)


def test_crisis_text_never_becomes_long_term_memory():
    from app.modules.student.assistant_mem0 import _compact_fact

    assert _compact_fact("我想跳楼", "我很担心你") == ""
    assert _compact_fact("我叫小明", "好的，小明") == "学生姓名：小明"


def test_high_risk_terms_are_unique_and_non_empty():
    assert len(set(HIGH_RISK_TERMS)) == len(HIGH_RISK_TERMS)
    assert all(term.strip() for term in HIGH_RISK_TERMS)
