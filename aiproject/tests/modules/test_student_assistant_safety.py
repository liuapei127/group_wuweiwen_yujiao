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


def test_chat_checks_crisis_before_identity_and_open_business_slots(monkeypatch):
    observed = []
    monkeypatch.setattr(chat, "_place_label", lambda *_: "德国")
    monkeypatch.setattr(chat, "_psych", lambda _db, _student, message, _history, _place: (
        observed.append(message) or {"reply": "关怀", "intent": "psych", "data": None}
    ))
    leave_history = [{"role": "assistant", "content": "好，先按病假。请再补充：起止日期。"}]
    feedback_history = [{"role": "assistant", "content": chat._feedback_choices()}]
    for message, history in (
        ("我叫测试同学，我不想活了", []),
        ("明天请假，我不想活了", leave_history),
        ("1，我不想活了", feedback_history),
    ):
        assert chat.handle_chat(object(), student_id=1, message=message, history=history)["intent"] == "psych"
    assert len(observed) == 3


def test_unassigned_crisis_remains_pending_and_can_be_claimed_only_in_scope(monkeypatch):
    from sqlalchemy import Column, Integer, MetaData, Table, create_engine, select
    from sqlalchemy.orm import Session

    from app.core.security import EmployeePrincipal
    from app.modules.student import alerts

    engine = create_engine("sqlite://")
    metadata = MetaData()
    for projection in (chat._psych_record, alerts._alert):
        Table(projection.name, metadata, Column("id", Integer, primary_key=True),
              *(Column(col.name, col.type) for col in projection.c if col.name != "id"))
    metadata.create_all(engine)
    monkeypatch.setattr(chat.StudentAdminRepository, "class_teacher", lambda *_: None)
    monkeypatch.setattr(chat, "_place_label", lambda *_: "德国")
    monkeypatch.setattr(chat, "speak", lambda *_, **__: None)
    permissions = frozenset({"student-alerts:read", "student-alerts:write"})
    teacher = EmployeePrincipal(10, permissions, student_ids=frozenset({1}))
    coworker = EmployeePrincipal(11, permissions, student_ids=frozenset({1}))
    unrelated = EmployeePrincipal(12, permissions, student_ids=frozenset({2}))
    with Session(engine) as db:
        result = chat.handle_chat(db, student_id=1, message="我叫测试同学，我不想活了")
        assert result["intent"] == "psych" and result["data"] is None
        assert db.scalar(select(chat._psych_record.c.id)) == 1
        [record] = alerts.list_alerts(db, teacher, None, 30)
        assert record.status == "pending" and record.teacher_id is None
        assert not alerts.list_alerts(db, unrelated, None, 30)
        claim = alerts.follow_alert(db, teacher, record.id, alerts.AlertUpdate(status="following", follow_record="已联系"))
        assert claim.teacher_id == 10
        assert not alerts.list_alerts(db, coworker, None, 30)
    engine.dispose()


def test_explicit_invalid_or_incomplete_leave_never_calls_submit(monkeypatch):
    from unittest.mock import Mock

    monkeypatch.setattr(chat, "_place_label", lambda *_: "德国")
    service = Mock()
    monkeypatch.setattr(chat, "StudentAdminServiceLayer", service)
    for span in ("25:00到26:00", "09:00到26:00", "09:70到10:00", "25:到26:", "09:00", "08:30、09:30"):
        outcome = chat.handle_chat(object(), student_id=1, message=f"病假，明天{span}，身体不适")
        assert outcome["intent"] == "leave_form", span
    service.assert_not_called()
    monkeypatch.setattr(chat.StudentAdminRepository, "class_teacher", lambda *_: None)
    service.return_value.submit_student_leave.return_value.id = 1
    service.return_value.submit_student_leave.return_value.model_dump.return_value = {}
    outcome = chat.handle_chat(object(), student_id=1, message="病假，明天09:30到11:10，身体不适")
    submitted = service.return_value.submit_student_leave.call_args.args[1]
    assert outcome["intent"] == "leave_submit"
    assert (submitted.start_time.strftime("%H:%M"), submitted.end_time.strftime("%H:%M")) == ("09:30", "11:10")


def test_open_leave_does_not_capture_queries_and_short_complaint_keeps_type(monkeypatch):
    from unittest.mock import Mock

    monkeypatch.setattr(chat, "_place_label", lambda *_: "德国")
    monkeypatch.setattr(chat, "_progress", lambda *_: {"reply": "申请进度", "intent": "progress", "data": None})
    file_complaint = Mock()
    monkeypatch.setattr(chat.feedback_service, "submit_student_complaint", file_complaint)
    leave_history = [{"role": "assistant", "content": "好，先按病假。请再补充：起止日期。"}]
    assert chat.handle_chat(object(), student_id=1, message="查进度", history=leave_history)["intent"] == "progress"

    history = []
    for message in ("我要投诉", "1", "老师针对我"):
        result = chat.handle_chat(object(), student_id=1, message=message, history=history)
        history += [{"role": "user", "content": message}, {"role": "assistant", "content": result["reply"]}]
    assert result["intent"] == "feedback_detail"
    assert result["data"]["ticket_type"] == "complaint"
    assert chat.handle_chat(object(), student_id=1, message="取消", history=history)["intent"] == "feedback_cancel"
    file_complaint.assert_not_called()
