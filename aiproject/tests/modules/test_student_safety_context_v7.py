"""Contextual safety dialogue only; no live model, credentials, or alerts."""
import asyncio
import pytest
from app.modules.student import assistant_dialogue as dialogue, assistant_workspace as workspace
from app.modules.student import assistant_dify, assistant_store
from tests.modules.test_student_workspace import db, prepare_turn, cid


def history(*words):
    return [{"role": "user", "content": word} for word in words]


def test_alone_then_location_then_ack_keeps_context_and_latest_location():
    turns=history("我想跳楼", "我一个人", "我在纽约")
    context=dialogue.safety_context("好", turns)
    assert context["active"] and context["alone"] is True
    assert context["self_reported_location"]["country"] == "US"
    assert context["self_reported_location"]["city"] == "New York"
    assert context["source"] == "current_conversation_user_statements"
    assert context["latest_user_message"] == "好"


@pytest.mark.parametrize("message", ["我一个人", "我现在没有人陪", "身边没人"])
def test_known_alone_fallback_does_not_ask_the_same_question(message):
    reply=dialogue.safety_reply(message, history("我想跳楼"), followup=True)
    assert "一个人" in reply or "没有人" in reply or "陪伴" in reply
    assert "身边有人可以陪你吗" not in reply
    assert "有人陪你吗" not in reply


def test_location_and_ok_fallback_are_specific_without_empty_resource_promise():
    turns=history("我想跳楼", "我一个人")
    reply=dialogue.safety_reply("我在纽约", turns, followup=True)
    assert "纽约" in reply and "有人陪你吗" not in reply
    assert "帮你找" not in reply and "正在查" not in reply
    turns.append({"role":"user", "content":"我在纽约"})
    assert dialogue.crisis_followup("好", turns)
    reply=dialogue.safety_reply("好", turns, followup=True)
    assert "安全" in reply and "国家" not in reply


@pytest.mark.parametrize("message", ["马云是谁？", "我想坐公交", "换个话题，地铁怎么买票"])
def test_explicit_unrelated_topic_stops_support_context(message):
    assert not dialogue.safety_context(message, history("我想跳楼", "我一个人"))["active"]


def test_assistant_and_quoted_or_negated_disclosure_are_not_student_risk_evidence():
    assert not dialogue.safety_context("我一个人", [{"role":"assistant", "content":"我想跳楼"}])["active"]
    for text in ("我不想自杀", "小说里写着‘我想自杀’", "同学说他想自杀", "如果有人想自杀怎么办", "我朋友想自杀", "他想自杀"):
        assert not dialogue.safety_context("我一个人", history(text))["active"]
    assert dialogue.safety_context("我一个人", history("朋友让我跳楼"))["active"]


def test_newer_negated_location_clears_old_location_and_question_is_not_evidence():
    state=dialogue.safety_context("好", history("我想跳楼", "我在德国", "我不在德国了"))
    assert state["active"] and state["self_reported_location"] is None
    state=dialogue.safety_context("我在纽约吗？", history("我想跳楼"))
    assert state["self_reported_location"] is None


def test_negated_safety_status_and_companion_changes_are_not_conflated():
    state=dialogue.safety_context("我现在不安全", history("我想跳楼", "朋友在陪我"))
    assert state["safety"] == "unsafe" and state["alone"] is False
    state=dialogue.safety_context("我已经在安全地方，朋友陪着我", history("我想跳楼", "我一个人"))
    assert state["safety"] == "safe" and state["alone"] is False


def test_safety_seed_is_immediate_then_one_contextual_generation(db, monkeypatch):
    prepare_turn(monkeypatch)
    seen=[]; calls=[]; alerts=[]
    def alert(*args, **kwargs):
        assert seen and "安全" in seen[0]
        assert kwargs["generate_reply"] is False
        alerts.append(kwargs["message"])
        return {"intent":"psych", "reply":"旧回复"}
    monkeypatch.setattr(workspace.legacy,"handle_chat", alert)
    async def visible(**kwargs):
        calls.append(kwargs)
        assert kwargs["kind"] == "safety_support"
        assert kwargs["initial_prefix"] == seen[0]
        assert kwargs["safety_context"]["current_disclosure"] is True
        assert kwargs["first_content_timeout"] == 12 and 0 < kwargs["overall_timeout"] <= 15
        return kwargs["initial_prefix"] + "请先联系一个信任的人，让他陪你一会儿。"
    monkeypatch.setattr(assistant_dify,"stream_reply",visible)
    monkeypatch.setattr(workspace.assistant_mem0,"remember_turn",lambda *a, **kw:pytest.fail("No crisis long-term memory"))
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="我想跳楼",conversation_id=None,use_dify=True,on_text=seen.append))
    assert len(calls)==1 and alerts==["我想跳楼"]
    assert result["reply"].startswith(seen[0]) and result["source"]=="dify"


def test_location_and_short_ack_send_owned_context_to_model_without_alerts(db,monkeypatch):
    prepare_turn(monkeypatch)
    conversation=cid(db)
    for text in ("我想跳楼", "我一个人", "我在纽约"):
        assistant_store.append_turn(db,student_id=2,conversation_id=conversation,user_text=text,assistant_text="之前的支持")
    calls=[]
    async def visible(**kwargs):
        calls.append(kwargs)
        assert kwargs["safety_context"]["alone"] is True
        assert kwargs["safety_context"]["self_reported_location"]["city"]=="New York"
        assert [x["content"] for x in kwargs["history"] if x["role"]=="user"]==["我想跳楼","我一个人","我在纽约"]
        assert kwargs["context"]["profile"]["school"]=="真实院校"
        assert kwargs["initial_prefix"]==""
        return "先按刚才的步骤，到有工作人员的安全地方。"
    monkeypatch.setattr(assistant_dify,"stream_reply",visible)
    monkeypatch.setattr(workspace.legacy,"handle_chat",lambda *a, **kw:pytest.fail("Do not replay alert"))
    monkeypatch.setattr(workspace.assistant_mem0,"remember_turn",lambda *a, **kw:pytest.fail("No crisis long-term memory"))
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="好",conversation_id=conversation,use_dify=True))
    assert len(calls)==1 and result["intent"]=="support"
    assert result["cards"] and "纽约" in str(result["cards"])


def test_ordinary_model_receives_ten_pairs_and_new_wait_budget(db,monkeypatch):
    prepare_turn(monkeypatch)
    conversation=cid(db)
    for i in range(12):
        assistant_store.append_turn(db,student_id=2,conversation_id=conversation,user_text=f"我的普通问题{i}",assistant_text=f"普通回复{i}")
    async def visible(**kwargs):
        assert len(kwargs["history"])==20
        assert kwargs["history"][0]["content"]=="我的普通问题2"
        assert kwargs["first_content_timeout"]==12 and 0 < kwargs["overall_timeout"]<=15
        return "理解本轮上下文的回复。"
    monkeypatch.setattr(assistant_dify,"stream_reply",visible)
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="你好",conversation_id=conversation,use_dify=True))
    assert result["source"]=="dify"


def test_safety_timeout_preserves_contextual_local_help_without_generic_greeting(db,monkeypatch):
    prepare_turn(monkeypatch)
    conversation=cid(db)
    assistant_store.append_turn(db,student_id=2,conversation_id=conversation,user_text="我想跳楼",assistant_text="之前支持")
    from app.modules.student.assistant_reply_stream import StudentReplyInterrupted
    async def failed(**kwargs):
        raise StudentReplyInterrupted(safe_partial=kwargs["initial_prefix"],reason_code="reply_timeout")
    monkeypatch.setattr(assistant_dify,"stream_reply",failed)
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="我一个人",conversation_id=conversation,use_dify=True))
    assert "安全" in result["reply"] and "陪伴" in result["reply"]
    assert "你好呀" not in result["reply"] and "有人陪你吗" not in result["reply"]
    assert result["reply_notice"]


def test_new_conversation_does_not_inherit_another_conversations_safety(db,monkeypatch):
    prepare_turn(monkeypatch)
    old=cid(db)
    assistant_store.append_turn(db,student_id=2,conversation_id=old,user_text="我想跳楼",assistant_text="支持")
    async def visible(**kwargs):
        assert kwargs["kind"]!="safety_support"
        assert "safety_context" not in kwargs
        return "普通交流。"
    monkeypatch.setattr(assistant_dify,"stream_reply",visible)
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="我一个人",conversation_id=None,use_dify=True))
    assert result["reply"]=="普通交流。"


@pytest.mark.parametrize("query", ["哪里能马上求助", "我该联系谁", "附近医院呢"])
def test_new_york_urgent_help_keeps_support_instead_of_academic_country(db,monkeypatch,query):
    prepare_turn(monkeypatch)
    conversation=cid(db)
    for text in ("我想跳楼", "我一个人", "我在纽约"):
        assistant_store.append_turn(db,student_id=2,conversation_id=conversation,user_text=text,assistant_text="支持")
    async def visible(**kwargs):
        assert kwargs["kind"]=="safety_support"
        assert kwargs["safety_context"]["self_reported_location"]["country"]=="US"
        return "先去有工作人员的安全地方，请他们协助你获得现实中的支持。"
    monkeypatch.setattr(assistant_dify,"stream_reply",visible)
    monkeypatch.setattr(workspace.knowledge,"answer",lambda *a,**kw:pytest.fail("Do not use academic-country life knowledge for urgent support"))
    result=asyncio.run(workspace.run_turn(db,student_id=2,query=query,conversation_id=conversation,use_dify=True))
    assert result["intent"]=="support" and "纽约" in str(result["cards"])


def test_legacy_speaker_can_be_disabled_without_changing_alert_writes(monkeypatch):
    from types import SimpleNamespace
    from app.modules.student import assistant_chat as legacy
    records=[]; notifications=[]; committed=[]
    fake_db=SimpleNamespace(execute=lambda statement:(records.append(statement.table.name) or SimpleNamespace(lastrowid=7)),commit=lambda:committed.append(True))
    monkeypatch.setattr(legacy.StudentAdminRepository,"class_teacher",lambda *a:4)
    monkeypatch.setattr(legacy,"speak",lambda *a,**kw:pytest.fail("No legacy generation in workspace safety path"))
    monkeypatch.setattr(legacy,"_staff_notify",lambda *a,**kw:notifications.append(kw))
    result=legacy._psych(fake_db,2,"我想跳楼",[],"德国方向",generate_reply=False)
    assert records==["student_psych_record","student_psych_alert"]
    assert len(notifications)==1 and notifications[0]["user_id"]==4
    assert notifications[0]["related_id"]==7 and committed==[True]
    assert result["intent"]=="psych" and result["data"] is None


def test_legacy_entry_keeps_reply_generation_by_default(monkeypatch):
    from app.modules.student import assistant_chat as legacy
    monkeypatch.setattr(legacy,"_place_label",lambda *a:"德国方向")
    seen=[]
    def psych(*args,generate_reply=True):
        seen.append(generate_reply)
        return {"intent":"psych","reply":"支持"}
    monkeypatch.setattr(legacy,"_psych",psych)
    legacy.handle_chat(None,student_id=2,message="我想跳楼")
    legacy.handle_chat(None,student_id=2,message="我想跳楼",generate_reply=False)
    assert seen==[True,False]


def test_leave_reason_draft_is_unchanged_by_crisis_companionship_location_and_ack(db,monkeypatch):
    prepare_turn(monkeypatch)
    from app.modules.student import assistant_tasks as tasks
    conversation=cid(db)
    draft=tasks.save_draft(db,2,conversation,"leave",{"leave_type":"sick","start_time":"2026-12-04T09:00:00","end_time":"2026-12-04T18:00:00"},None)
    assistant_store.append_turn(db,student_id=2,conversation_id=conversation,user_text="我想跳楼",assistant_text="支持")
    async def visible(**kwargs):
        assert kwargs["kind"]=="safety_support"
        return kwargs["reviewed_reply"]
    monkeypatch.setattr(assistant_dify,"stream_reply",visible)
    for query in ("我一个人","我在纽约","好"):
        result=asyncio.run(workspace.run_turn(db,student_id=2,query=query,conversation_id=conversation,use_dify=True))
        assert result["intent"]=="support"
        assert result["task"]["id"]==draft["id"] and result["task"]["version"]==draft["version"]


def test_safety_timeout_without_seed_still_has_contextual_help_and_location_cards(db,monkeypatch):
    prepare_turn(monkeypatch)
    conversation=cid(db)
    for text in ("我想跳楼","我一个人","我在纽约"):
        assistant_store.append_turn(db,student_id=2,conversation_id=conversation,user_text=text,assistant_text="支持")
    from app.modules.student.assistant_reply_stream import StudentReplyInterrupted
    async def failed(**kwargs):
        assert kwargs["initial_prefix"]==""
        raise StudentReplyInterrupted(safe_partial="",reason_code="reply_timeout")
    monkeypatch.setattr(assistant_dify,"stream_reply",failed)
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="好",conversation_id=conversation,use_dify=True))
    assert result["source"]=="local_safety_fallback"
    assert "安全" in result["reply"] and "陪" in result["reply"]
    assert "纽约" in str(result["cards"])
    assert "你好呀" not in result["reply"] and "未能完成" not in result["reply"]


def test_new_direct_risk_is_not_overridden_by_earlier_safe_status():
    turns=history("我想跳楼","我已经在安全地方，朋友陪着我")
    state=dialogue.safety_context("我想跳楼",turns)
    assert state["current_disclosure"] and state["safety"]!="safe"
    reply=dialogue.safety_reply("我想跳楼",turns,context=state)
    assert reply.startswith(dialogue.safety_initial_prefix("我想跳楼",turns,context=state))
    assert not reply.startswith("谢谢你告诉我")


@pytest.mark.parametrize("message", ["我现在安全不了","我不能保证自己安全","无法保证自身安全"])
def test_negative_safety_semantics_cannot_keep_an_older_safe_status(message):
    state=dialogue.safety_context(message,history("我想跳楼","我现在安全了"))
    assert state["active"] and state["safety"]=="unsafe"


def test_planning_and_visible_generation_share_one_fifteen_second_budget(db,monkeypatch):
    prepare_turn(monkeypatch)
    clock=iter([100.0,107.0])
    monkeypatch.setattr(workspace,"monotonic",lambda:next(clock))
    monkeypatch.setattr(workspace,"_needs_field_understanding",lambda *a:True)
    from app.modules.student.schemas import AssistantUnderstanding
    async def understand(**kwargs):return AssistantUnderstanding(intent="chat")
    async def visible(**kwargs):
        assert kwargs["overall_timeout"]==8 and kwargs["first_content_timeout"]==8
        return "上下文回复。"
    monkeypatch.setattr(assistant_dify,"understand",understand)
    monkeypatch.setattr(assistant_dify,"stream_reply",visible)
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="你好",conversation_id=None,use_dify=True))
    assert result["reply"]=="上下文回复。"


@pytest.mark.parametrize("message", ["我在申请德国", "我在研究纽约", "我在考虑新加坡", "我在公司的网站查看德国资料"])
def test_current_activity_is_not_promoted_to_a_location(message):
    state=dialogue.safety_context(message,history("我想跳楼"))
    assert state["self_reported_location"] is None


def test_question_about_safety_does_not_establish_recovery():
    state=dialogue.safety_context("我现在安全吗？",history("我想跳楼"))
    assert state["active"] and state["safety"]!="safe"


def test_recent_explicit_current_location_before_disclosure_is_available_and_can_be_cleared():
    state=dialogue.safety_context("我想跳楼",history("我现在在纽约"))
    assert state["active"] and state["self_reported_location"]["country"]=="US"
    assert state["self_reported_location"]["evidence"]=="我现在在纽约"
    state=dialogue.safety_context("我想跳楼",history("我现在在纽约","我现在不在纽约了"))
    assert state["self_reported_location"] is None
    state=dialogue.safety_context("我想跳楼",history("我现在在纽约","我现在在新加坡"))
    assert state["self_reported_location"]["country"]=="Singapore"


def test_confirmed_safe_fallback_asks_about_unknown_companion_instead_of_safety_again():
    reply=dialogue.safety_reply("我现在安全了",history("我想跳楼"),followup=True)
    assert "你说已经到了安全的地方" in reply
    assert "你现在在安全的地方吗" not in reply and "陪伴" in reply


def test_new_unsupported_city_with_accommodation_suffix_replaces_old_country():
    state=dialogue.safety_context("我现在在东京的宿舍",history("我想跳楼","我在纽约"))
    assert state["active"] and state["self_reported_location"]["country"] is None
    assert state["self_reported_location"]["label"]=="东京的宿舍"
