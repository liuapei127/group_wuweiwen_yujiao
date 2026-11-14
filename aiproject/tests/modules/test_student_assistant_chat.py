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
