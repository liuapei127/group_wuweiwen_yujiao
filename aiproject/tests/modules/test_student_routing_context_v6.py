"""V6 regressions: relevant routing and same-account crisis continuity, no live alerts."""
import asyncio
import pytest
from app.modules.student import assistant_workspace as workspace, assistant_dify, assistant_store
from tests.modules.test_student_workspace import db, prepare_turn, cid
from tests.modules.test_student_experience import knowledge_db

@pytest.mark.parametrize("country", ["Germany", "Singapore"])
@pytest.mark.parametrize("query", ["不了解当地的交通情况", "当地交通怎么安排", "想了解公共交通"])
def test_transport_overview_uses_existing_reviewed_content(knowledge_db, country, query):
    result = workspace.knowledge.answer(knowledge_db, country, query)
    assert result.get("knowledge_keys")
    assert all(key.startswith(country + "/transport/") for key in result["knowledge_keys"])
    assert len(result["cards"]) == 1 and len(result["reply"]) < 260
    assert "没有查到" not in result["reply"]

@pytest.mark.parametrize("query", ["马云是谁", "马云是谁？", "什么是光合作用", "法国的首都是哪里"])
def test_general_factual_questions_get_one_general_generation(db, monkeypatch, query):
    prepare_turn(monkeypatch)
    async def no_plan(**kwargs): pytest.fail("No business plan for general questions")
    async def visible(**kwargs):
        assert kwargs["kind"] == "general"
        return "针对这个常识问题的回答。"
    monkeypatch.setattr(assistant_dify, "understand", no_plan)
    monkeypatch.setattr(assistant_dify, "stream_reply", visible)
    result = asyncio.run(workspace.run_turn(db, student_id=2, query=query, conversation_id=None, use_dify=True))
    assert result["reply"] == "针对这个常识问题的回答。"
    assert result["task"] is None


def test_crisis_followup_is_same_conversation_and_does_not_create_another_alert(db, monkeypatch):
    prepare_turn(monkeypatch)
    alerts = []
    def fake_alert(*args, **kwargs):
        alerts.append(kwargs["message"])
        return {"intent":"psych", "reply":"旧的回复"}
    monkeypatch.setattr(workspace.legacy, "handle_chat", fake_alert)
    async def no_model(**kwargs):
        assert kwargs["kind"] == "safety_support"
        return kwargs["reviewed_reply"]
    monkeypatch.setattr(assistant_dify, "stream_reply", no_model)
    conversation = cid(db)
    first = asyncio.run(workspace.run_turn(db, student_id=2, query="我想跳楼", conversation_id=conversation, use_dify=True))
    assert "安全" in first["reply"] and "远离" in first["reply"]
    follow = asyncio.run(workspace.run_turn(db, student_id=2, query="因为班主任打压我", conversation_id=conversation, use_dify=True))
    assert follow["intent"] == "support" and "安全" in follow["reply"]
    assert "其他" in follow["reply"] and "班主任和学校心理支持都可以" not in follow["reply"]
    assert follow["task"] is None and alerts == ["我想跳楼"]
    third = asyncio.run(workspace.run_turn(db, student_id=2, query="我不知道该怎么办", conversation_id=conversation, use_dify=True))
    assert "安全" in third["reply"] and alerts == ["我想跳楼"]


def test_old_crisis_does_not_capture_explicit_new_topic_or_another_conversation(db, monkeypatch):
    prepare_turn(monkeypatch)
    conversation = cid(db)
    assistant_store.append_turn(db, student_id=2, conversation_id=conversation, user_text="我想跳楼", assistant_text="安全支持")
    seen=[]
    async def visible(**kwargs):
        seen.append(kwargs["kind"])
        return "一般问题回答"
    monkeypatch.setattr(assistant_dify, "stream_reply", visible)
    result = asyncio.run(workspace.run_turn(db, student_id=2, query="我现在安全了，谢谢。我想问马云是谁", conversation_id=conversation, use_dify=True))
    assert result["reply"] == "一般问题回答" and seen == ["general"]
    other = asyncio.run(workspace.run_turn(db, student_id=2, query="你好", conversation_id=None, use_dify=True))
    assert other["intent"] == "chat" and seen[-1] == "chat"


def test_complaint_does_not_follow_from_emotional_teacher_disclosure(db, monkeypatch):
    prepare_turn(monkeypatch)
    async def visible(**kwargs): return "我在听，可以慢慢说。"
    monkeypatch.setattr(assistant_dify, "stream_reply", visible)
    result = asyncio.run(workspace.run_turn(db, student_id=2, query="班主任打压我，我很难受", conversation_id=None, use_dify=True))
    assert result["intent"] == "support" and result["task"] is None
    explicit = asyncio.run(workspace.run_turn(db, student_id=2, query="我要正式投诉班主任打压我", conversation_id=None, use_dify=False))
    assert explicit["intent"] == "feedback" and explicit["task"]["status"] in ("collecting", "awaiting_confirmation")


def test_general_failure_is_honest_and_never_generic_greeting(db, monkeypatch):
    prepare_turn(monkeypatch)
    from app.core.exceptions import BusinessError
    async def unavailable(**kwargs): raise BusinessError(503, "generation unavailable")
    monkeypatch.setattr(assistant_dify, "stream_reply", unavailable)
    result = asyncio.run(workspace.run_turn(db, student_id=2, query="马云是谁", conversation_id=None, use_dify=True))
    assert "未能" in result["reply"] or "没能" in result["reply"]
    assert "你好呀" not in result["reply"] and "没能" in result["reply"]


@pytest.mark.parametrize("partial", ["马云是一位中国企业家。", ""])
def test_interrupted_reply_keeps_only_checked_prefix_and_persists_notice(db, monkeypatch, partial):
    prepare_turn(monkeypatch)
    from app.modules.student.assistant_reply_stream import StudentReplyInterrupted
    async def interrupted(**kwargs):
        if partial:
            kwargs["on_text"](partial)
        raise StudentReplyInterrupted(safe_partial=partial, reason_code="reply_rejected")
    monkeypatch.setattr(assistant_dify, "stream_reply", interrupted)
    seen=[]
    result = asyncio.run(workspace.run_turn(db, student_id=2, query="马云是谁", conversation_id=None, use_dify=True, on_text=seen.append))
    assert "" not in seen
    if partial:
        assert result["reply"] == partial and seen == [partial]
        assert result["source"] == "dify_partial"
    else:
        assert "没能" in result["reply"] and "你好呀" not in result["reply"]
    stored = assistant_store.list_messages(db, result["conversation_id"])[-1]
    assert stored["content"] == result["reply"]
    assert stored["presentation"]["reply_notice"] == result["reply_notice"]


def test_explicit_complaint_after_crisis_is_still_a_draft_not_an_alert(db, monkeypatch):
    prepare_turn(monkeypatch)
    conversation=cid(db)
    assistant_store.append_turn(db, student_id=2, conversation_id=conversation, user_text="我想跳楼", assistant_text="安全支持")
    result=asyncio.run(workspace.run_turn(db, student_id=2, query="我要正式投诉班主任打压我", conversation_id=conversation, use_dify=False))
    assert result["intent"] == "feedback" and result["task"]


def test_assistant_claims_and_another_accounts_history_cannot_create_crisis_context(db, monkeypatch):
    prepare_turn(monkeypatch)
    conversation=cid(db, sid=3)
    assistant_store.append_turn(db, student_id=3, conversation_id=conversation, user_text="你好", assistant_text="我想跳楼")
    from app.modules.student import assistant_dialogue as dialogue
    assert not dialogue.crisis_followup("因为班主任打压我", assistant_store.recent_turns(db, conversation))
    from app.core.exceptions import BusinessError
    with pytest.raises(BusinessError):
        asyncio.run(workspace.run_turn(db, student_id=2, query="因为班主任打压我", conversation_id=conversation, use_dify=False))


@pytest.mark.parametrize("query", ["我现在一个人", "没事了我已经和朋友在一起"])
def test_safety_followups_are_immediate_and_not_long_term_memories(db, monkeypatch, query):
    prepare_turn(monkeypatch)
    conversation=cid(db)
    assistant_store.append_turn(db, student_id=2, conversation_id=conversation, user_text="我想跳楼", assistant_text="安全支持")
    async def forbidden(**kwargs):
        assert kwargs["kind"] == "safety_support"
        return kwargs["reviewed_reply"]
    monkeypatch.setattr(assistant_dify, "stream_reply", forbidden)
    monkeypatch.setattr(workspace.assistant_mem0, "remember_turn", lambda *a, **kw: pytest.fail("Do not retain crisis disclosures as long-term memory"))
    result=asyncio.run(workspace.run_turn(db, student_id=2, query=query, conversation_id=conversation, use_dify=True))
    assert result["intent"] == "support" and "安全" in result["reply"]


def test_new_transport_topic_ends_crisis_context_without_claiming_recovery(db, monkeypatch):
    prepare_turn(monkeypatch)
    conversation=cid(db)
    assistant_store.append_turn(db, student_id=2, conversation_id=conversation, user_text="我想跳楼", assistant_text="安全支持")
    monkeypatch.setattr(workspace.knowledge, "answer", lambda *a, **kw: {"intent":"ask", "reply":"公交审核说明", "knowledge_keys":["Germany/transport/3"]})
    result=asyncio.run(workspace.run_turn(db, student_id=2, query="我想坐公交", conversation_id=conversation, use_dify=False))
    assert result["reply"] == "公交审核说明" and result["intent"] == "ask"
    from app.modules.student import assistant_dialogue as dialogue
    history=assistant_store.recent_turns(db, conversation)
    assert not dialogue.crisis_followup("我不知道该怎么办", history)


def test_current_crisis_is_not_long_term_memory(db, monkeypatch):
    prepare_turn(monkeypatch)
    monkeypatch.setattr(workspace.legacy, "handle_chat", lambda *a, **kw: {"intent":"psych", "reply":"旧回复"})
    monkeypatch.setattr(workspace.assistant_mem0, "remember_turn", lambda *a, **kw: pytest.fail("No crisis long-term memory"))
    result=asyncio.run(workspace.run_turn(db, student_id=2, query="我想跳楼", conversation_id=None, use_dify=False))
    assert result["intent"] == "psych" and "安全" in result["reply"]


@pytest.mark.parametrize("query", ["我在哪留学", "我的留学去向"])
def test_personal_destination_is_official_profile_and_not_general(db, monkeypatch, query):
    prepare_turn(monkeypatch)
    async def forbidden(**kwargs): pytest.fail("Official student records must not be generated")
    monkeypatch.setattr(assistant_dify, "stream_reply", forbidden)
    result=asyncio.run(workspace.run_turn(db, student_id=2, query=query, conversation_id=None, use_dify=True))
    assert result["intent"] == "profile" and result["facts_kind"] == "student_record"


def test_name_recall_is_self_reported_memory_and_not_general_generation(db, monkeypatch):
    prepare_turn(monkeypatch)
    async def forbidden(**kwargs): pytest.fail("Memory recall must not be replaced by generated personal facts")
    monkeypatch.setattr(assistant_dify, "stream_reply", forbidden)
    monkeypatch.setattr(workspace.assistant_mem0, "search_memories", lambda *a, **kw: [])
    result=asyncio.run(workspace.run_turn(db, student_id=2, query="我叫什么名字", conversation_id=None, use_dify=True))
    assert "称呼" in result["reply"] and "还没有" in result["reply"]


def test_general_question_cannot_be_swallowed_as_active_feedback_content(db, monkeypatch):
    prepare_turn(monkeypatch)
    from app.modules.student import assistant_tasks as tasks
    conversation=cid(db)
    draft=tasks.save_draft(db, 2, conversation, "feedback", {}, None)
    async def visible(**kwargs):
        assert kwargs["kind"] == "general"
        return "光合作用是植物利用光能的过程。"
    monkeypatch.setattr(assistant_dify, "stream_reply", visible)
    result=asyncio.run(workspace.run_turn(db, student_id=2, query="什么是光合作用", conversation_id=conversation, use_dify=True))
    assert result["reply"].startswith("光合作用")
    assert result["task"]["id"] == draft["id"] and result["task"]["version"] == draft["version"]


@pytest.mark.parametrize("query", ["你能陪着我吗？", "我该怎么办？", "能帮帮我吗？"])
def test_actual_question_forms_still_continue_safety_support(db, monkeypatch, query):
    prepare_turn(monkeypatch)
    conversation=cid(db)
    assistant_store.append_turn(db, student_id=2, conversation_id=conversation, user_text="我想跳楼", assistant_text="安全支持")
    async def forbidden(**kwargs):
        assert kwargs["kind"] == "safety_support"
        return kwargs["reviewed_reply"]
    monkeypatch.setattr(assistant_dify, "stream_reply", forbidden)
    result=asyncio.run(workspace.run_turn(db, student_id=2, query=query, conversation_id=conversation, use_dify=True))
    assert result["intent"] == "support" and "安全" in result["reply"]


def test_unrelated_old_teacher_complaint_does_not_become_new_crisis_cause():
    from app.modules.student import assistant_dialogue as dialogue
    history=[{"role":"user", "content":"班主任打压我"}, {"role":"user", "content":"公交怎么坐"},
             {"role":"user", "content":"我想跳楼"}]
    reply=dialogue.safety_reply("我该怎么办？", history, followup=True)
    assert "班主任" not in reply
    reply=dialogue.safety_reply("我想跳楼", history, followup=False)
    assert "班主任" not in reply


@pytest.mark.parametrize("query", ["你好", "我有点累", "马云是谁"])
def test_uncertified_failure_reports_unfinished_instead_of_template(db, monkeypatch, query):
    prepare_turn(monkeypatch)
    from app.core.exceptions import BusinessError
    async def unavailable(**kwargs): raise BusinessError(503, "unavailable")
    monkeypatch.setattr(assistant_dify, "stream_reply", unavailable)
    result=asyncio.run(workspace.run_turn(db, student_id=2, query=query, conversation_id=None, use_dify=True))
    assert any(word in result["reply"] for word in ("未能完成", "没能完成"))
    assert result["reply_notice"] == "回复中断，请重试"



def test_crisis_explanation_does_not_fill_an_older_feedback_draft(db, monkeypatch):
    prepare_turn(monkeypatch)
    from app.modules.student import assistant_tasks as tasks
    conversation=cid(db)
    draft=tasks.save_draft(db, 2, conversation, "feedback", {}, None)
    assistant_store.append_turn(db, student_id=2, conversation_id=conversation, user_text="我想跳楼", assistant_text="安全支持")
    async def forbidden(**kwargs):
        assert kwargs["kind"] == "safety_support"
        return kwargs["reviewed_reply"]
    monkeypatch.setattr(assistant_dify, "stream_reply", forbidden)
    monkeypatch.setattr(assistant_dify, "understand", forbidden)
    result=asyncio.run(workspace.run_turn(db, student_id=2, query="因为班主任打压我", conversation_id=conversation, use_dify=True))
    assert result["intent"] == "support" and "安全" in result["reply"]
    assert result["task"]["id"] == draft["id"] and result["task"]["version"] == draft["version"]


@pytest.mark.parametrize("status", ["我现在不安全了", "我现在没有人陪"])
def test_negated_safety_status_does_not_resolve_or_drop_subsequent_help(db, monkeypatch, status):
    prepare_turn(monkeypatch)
    conversation=cid(db)
    assistant_store.append_turn(db, student_id=2, conversation_id=conversation, user_text="我想跳楼", assistant_text="安全支持")
    async def forbidden(**kwargs):
        assert kwargs["kind"] == "safety_support"
        return kwargs["reviewed_reply"]
    monkeypatch.setattr(assistant_dify, "stream_reply", forbidden)
    first=asyncio.run(workspace.run_turn(db, student_id=2, query=status, conversation_id=conversation, use_dify=True))
    assert first["intent"] == "support" and "安全" in first["reply"]
    assert not first["reply"].startswith("谢谢你告诉我")
    second=asyncio.run(workspace.run_turn(db, student_id=2, query="帮帮我", conversation_id=conversation, use_dify=True))
    assert second["intent"] == "support" and "安全" in second["reply"]


def test_asking_about_same_teacher_distress_is_not_a_topic_switch(db, monkeypatch):
    prepare_turn(monkeypatch)
    conversation=cid(db)
    assistant_store.append_turn(db, student_id=2, conversation_id=conversation, user_text="我想跳楼", assistant_text="安全支持")
    async def forbidden(**kwargs):
        assert kwargs["kind"] == "safety_support"
        return kwargs["reviewed_reply"]
    monkeypatch.setattr(assistant_dify, "stream_reply", forbidden)
    result=asyncio.run(workspace.run_turn(db, student_id=2, query="我想问为什么班主任打压我", conversation_id=conversation, use_dify=True))
    assert result["intent"] == "support" and "安全" in result["reply"] and "其他" in result["reply"]


@pytest.mark.parametrize("query,intent", [("我现在在德国吗？", "location"), ("我已经入学了吗？", "profile")])
def test_self_location_or_stage_question_is_not_a_general_factual_question(db, monkeypatch, query, intent):
    prepare_turn(monkeypatch)
    from app.modules.student import assistant_dialogue as dialogue
    assert not dialogue.general_question(query)
    async def forbidden(**kwargs): pytest.fail("Student state cannot be guessed by the general model")
    monkeypatch.setattr(assistant_dify, "stream_reply", forbidden)
    result=asyncio.run(workspace.run_turn(db, student_id=2, query=query, conversation_id=None, use_dify=True))
    assert result["intent"] == intent
    assert "你已经入学" not in result["reply"] and "你现在在德国生活" not in result["reply"]
