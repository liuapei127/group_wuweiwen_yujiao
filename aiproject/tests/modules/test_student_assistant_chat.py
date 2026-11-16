"""Unit tests for spoken student assistant (no DB)."""

from app.modules.student.assistant_chat import (
    form_reply,
    leave_form,
    parse_filled_form,
    _follow_choice,
)
from app.modules.student.assistant_intent import route
from app.modules.student.assistant_speak import student_safe


def test_route_leave_and_psych():
    assert route("我要请假")["intent"] == "leave_create"
    assert route("我的请假批了吗")["intent"] == "leave_query"
    assert route("想家心情不好")["intent"] == "psych"
    assert route("查留学进度")["intent"] == "progress"
    assert route("查进度")["intent"] == "progress"
    assert route("查询签证怎么办")["intent"] == "ask"
    assert route("宿舍环境太差了")["intent"] == "feedback"


def test_chat_reply_never_dumps_memory():
    from app.modules.student.assistant_chat import _chat_reply

    reply = _chat_reply(
        "随便说说",
        "德国方向",
        [],
        ["学生姓名：木合塔尔", "学生说：17号号到19号；助手答复要点：还没对上"],
    )
    assert "学生说：" not in reply
    assert "助手答复要点" not in reply
    assert "我记得你之前提过" not in reply


def test_bare_digit_not_feedback_without_menu():
    from app.modules.student.assistant_chat import _picked_feedback

    assert _picked_feedback("1") is None
    assert _picked_feedback("1", [{"role": "assistant", "content": "回 1 正式投诉，回 2 提建议，回 3 先咨询。"}]) == (
        "complaint",
        "正式投诉",
    )


def test_parse_filled_leave_form():
    text = (
        "请假类型：病假\n"
        "开始时间：2026-11-20T09:00:00\n"
        "结束时间：2026-11-20T18:00:00\n"
        "事由：身体不适"
    )
    filled = parse_filled_form(text)
    assert filled is not None
    assert filled["leave_type"] == "sick"
    assert filled["reason"] == "身体不适"


def test_parse_date_only_leave_form():
    text = "请假类型：病假 开始时间：2026-11-17 结束时间：2026-11-19 事由：页面联调测试"
    filled = parse_filled_form(text)
    assert filled is not None
    assert filled["leave_type"] == "sick"
    assert filled["start_time"].day == 17
    assert filled["end_time"].day == 19
    assert filled["reason"] == "页面联调测试"


def test_natural_leave_date_range():
    from app.modules.student.assistant_chat import _natural_leave

    filled = _natural_leave("病假，2026-11-17 到 2026-11-19，身体不适要看病")
    assert filled is not None
    assert filled["leave_type"] == "sick"
    assert filled["reason"]


def test_leave_followup_day_range_keeps_context():
    from app.modules.student.assistant_chat import _follow_choice, _natural_leave, _compose_leave_utterance

    history = [
        {"role": "user", "content": "我想请假 肚子疼"},
        {"role": "assistant", "content": "好，先按病假。请再补充：起止日期，比如 2026-11-17 到 2026-11-19。也可以一口气说完，我会直接帮你交。"},
    ]
    forced, spoken = _follow_choice("17号号到19号", history)
    assert forced == "leave"
    assert "肚子疼" in spoken or "病假" in spoken
    filled = _natural_leave(_compose_leave_utterance("17号到19号", history), history)
    assert filled is not None
    assert filled["leave_type"] == "sick"
    assert filled["start_time"].day == 17
    assert filled["end_time"].day == 19


def test_leave_followup_after_user_leave_even_without_menu():
    from app.modules.student.assistant_chat import _follow_choice

    history = [
        {"role": "user", "content": "我想请假 肚子疼"},
        {"role": "assistant", "content": "今天已提交过相同时间段的请假。换一组日期再说一次。"},
    ]
    forced, spoken = _follow_choice("28号到29号", history)
    assert forced == "leave"
    assert "肚子疼" in spoken or "28" in spoken


def test_new_dates_replace_old_ones_after_duplicate_warning():
    """学生换一组日期再说时，不能再拿上一轮的旧日期去判重复。"""
    from app.modules.student.assistant_chat import _compose_leave_utterance, _natural_leave

    history = [
        {"role": "user", "content": "病假，2026-11-20 到 2026-11-21，发烧要看病"},
        {"role": "assistant", "content": "今天已提交过相同时间段的请假。换一组日期再说一次。"},
    ]
    filled = _natural_leave(
        _compose_leave_utterance("病假，2026-12-02 到 2026-12-03，发烧要看病", history), history
    )
    assert filled is not None
    assert filled["start_time"].date().isoformat() == "2026-12-02"
    assert filled["end_time"].date().isoformat() == "2026-12-03"


def test_reason_only_followup_reuses_previous_dates():
    from app.modules.student.assistant_chat import _compose_leave_utterance, _natural_leave

    history = [
        {"role": "user", "content": "病假，2026-12-02 到 2026-12-03"},
        {"role": "assistant", "content": "请再补充请假原因。"},
    ]
    filled = _natural_leave(_compose_leave_utterance("发烧了", history), history)
    assert filled is not None
    assert filled["start_time"].date().isoformat() == "2026-12-02"
    assert "发烧" in filled["reason"]


def test_complaint_trigger_alone_is_not_filed():
    """「我要投诉」只是开场白，不能直接开一张内容为空话的工单。"""
    from app.modules.student.assistant_chat import _has_substance

    assert not _has_substance("我要投诉")
    assert not _has_substance("我想提建议。")
    assert not _has_substance("我要投诉宿舍管理")
    assert _has_substance("德语老师上周当着全班骂我")
    # 已经追问过细节时，短一点的回答也要能落地
    assert _has_substance("老师针对我", 4)


def test_feedback_detail_followup_and_business_switch():
    from app.modules.student.assistant_chat import _feedback_detail_pending, _follow_choice

    history = [
        {"role": "user", "content": "我要投诉"},
        {"role": "assistant", "content": "听起来挺让人烦心的。\n你想怎么处理？回 1 正式投诉，回 2 提建议，回 3 先咨询。"},
        {"role": "user", "content": "1"},
        {"role": "assistant", "content": "好，正式投诉。说说具体是哪件事：什么时候、涉及谁、发生了什么？你说完我按正式投诉记下来。"},
    ]
    assert _feedback_detail_pending(history) == "complaint"
    forced, spoken = _follow_choice("德语老师上周当着全班骂我", history)
    assert forced == "feedback"
    assert "德语老师" in spoken
    # 学生中途换业务，不能被投诉正文吞掉
    assert _follow_choice("我要请假", history)[0] is None
    assert _follow_choice("我不想活了", history)[0] is None


def test_identity_name_and_who_am_i():
    from app.modules.student.assistant_chat import _asks_who_am_i, _heard_name, _identity_reply

    assert _heard_name("你好我叫木合塔尔") == "木合塔尔"
    assert _heard_name("你还记得我叫什么吗") == ""
    assert _asks_who_am_i("我是谁")
    assert _asks_who_am_i("你还记得我叫什么吗")
    reply = _identity_reply("我是谁", "德国方向", ["学生姓名：木合塔尔"])
    assert "木合塔尔" in reply["reply"]
    ask = _identity_reply("你还记得我叫什么吗", "德国方向", ["学生姓名：小明"], just_told="")
    assert "小明" in ask["reply"]
    assert "什么吗" not in ask["reply"]


def test_name_intro_beats_leave_pending():
    from app.modules.student import assistant_chat

    history = [
        {"role": "user", "content": "我想请假 肚子疼"},
        {"role": "assistant", "content": "好，先按病假。请再补充：起止日期。"},
    ]
    out = assistant_chat.handle_chat(
        db=None,  # type: ignore[arg-type]
        student_id=1,
        message="我叫小明",
        history=history,
        mock_country="Germany",
        memory_notes=[],
    )
    assert out["intent"] == "identity"
    assert "小明" in out["answer"]


def test_leave_form_points_to_v1_student_leaves():
    form = leave_form(3)
    assert form["submit"]["path"] == "/api/v1/student/leaves"


def test_follow_choice_leave_number():
    history = [{"role": "assistant", "content": "可以请假。先选一种：1. 病假 2. 事假 3. 紧急"}]
    forced, spoken = _follow_choice("1", history)
    assert forced == "leave"
    assert "病假" in spoken


def test_student_safe_strips_paths_and_ids():
    text = student_safe("好的 POST /api/v1/student/leaves 请假#12 已写入")
    assert "/api/" not in text
    assert "#12" not in text


def test_form_reply_asks_for_type_first():
    reply = form_reply("我要请假")
    assert "病假" in reply


def test_life_answer_looks_up_topic_and_passes_document_body(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import Mock

    from app.modules.student import assistant_chat as chat

    monkeypatch.setattr(chat.student_service, "student_policies", lambda *_: (
        SimpleNamespace(resources=[], country="Germany")
    ))
    lookup = Mock(side_effect=lambda _db, _student, keyword, *_: {"items": (
        [{"id": 1, "title": "公交指南", "content": "使用城市通票"}] if keyword == "公交" else []
    )})
    answer = Mock(return_value="可以使用城市通票")
    monkeypatch.setattr(chat.student_service, "overseas_resources", lookup)
    monkeypatch.setattr(chat, "speak", answer)
    assert "公交指南" in chat._ask(object(), 1, "在德国怎么坐公交", "德国")["reply"]
    assert "使用城市通票" in answer.call_args.args[0]
    assert lookup.call_args.args[2] == "公交"
    answer.reset_mock()
    assert chat._ask(object(), 1, "在德国怎么开户", "德国")["data"]["overseas_count"] == 0
    answer.assert_not_called()
