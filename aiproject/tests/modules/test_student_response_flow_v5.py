"""Regression: direct verified answers, contextual followups and one-call dialogue."""
import asyncio
import pytest
from app.modules.student import assistant_workspace as workspace, assistant_dify, assistant_store
from app.modules.student.schemas import AssistantUnderstanding
from app.core.exceptions import BusinessError
from tests.modules.test_student_workspace import db, prepare_turn, cid

def fail_model(monkeypatch):
    async def forbidden(**kwargs):
        pytest.fail("A directly answerable query must not wait for a model")
    monkeypatch.setattr(assistant_dify, "understand", forbidden)
    monkeypatch.setattr(assistant_dify, "stream_reply", forbidden)

def test_verified_public_answer_is_immediate_and_does_not_call_model(db, monkeypatch):
    prepare_turn(monkeypatch)
    fail_model(monkeypatch)
    answer = {"intent":"ask","reply":"上车和下车使用同一张适用卡片感应。","knowledge_keys":["Singapore/transport/4"],
              "facts_kind":"public_knowledge","cards":[{"title":"公交乘坐","fields":[],"source_url":"https://example.test/official"}]}
    monkeypatch.setattr(workspace.knowledge, "answer", lambda *a,**k:answer.copy())
    seen=[]
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="新加坡公交怎么坐",conversation_id=None,use_dify=True,on_text=seen.append))
    assert result["source"]=="reviewed_knowledge"
    assert seen==[answer["reply"]]
    assert assistant_store.list_messages(db,result["conversation_id"])[-1]["presentation"]["facts_kind"]=="public_knowledge"

def test_verified_contextual_followup_routes_to_knowledge_without_another_model(db, monkeypatch):
    prepare_turn(monkeypatch)
    fail_model(monkeypatch)
    conversation=cid(db)
    assistant_store.append_turn(db,student_id=2,conversation_id=conversation,user_text="我在新加坡，公交怎么坐",assistant_text="上车感应。")
    monkeypatch.setattr(workspace.knowledge,"resolve_question",
        lambda query,history=(): {"query":"新加坡公交乘车需要注册吗","category":"transport","subject":"bus","contextual":True,"concise":False,"detailed":False},raising=False)
    def answer(*args,**kwargs):
        assert kwargs["original_query"]=="那需要注册吗？"
        assert kwargs["history"][-2]["content"]=="我在新加坡，公交怎么坐"
        return {"intent":"ask","reply":"使用符合条件的卡片乘车不必先注册账号。","knowledge_keys":["Singapore/transport/0"],"facts_kind":"public_knowledge"}
    monkeypatch.setattr(workspace.knowledge,"answer",answer)
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="那需要注册吗？",conversation_id=conversation,use_dify=True,on_text=lambda _:None))
    assert result["intent"]=="ask" and result["source"]=="reviewed_knowledge"

def test_ordinary_dialogue_has_one_visible_call_without_planning(db, monkeypatch):
    prepare_turn(monkeypatch)
    async def planning(**kwargs):pytest.fail("Ordinary conversation must not make a planning call")
    calls=[]
    async def visible(**kwargs):
        calls.append(kwargs)
        assert kwargs["first_content_timeout"]==12
        assert 0 < kwargs["overall_timeout"]<=15
        kwargs["on_text"]("我在听。")
        return "我在听。你想先聊哪件事？"
    monkeypatch.setattr(assistant_dify,"understand",planning)
    monkeypatch.setattr(assistant_dify,"stream_reply",visible)
    seen=[]
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="你好，可以陪我聊聊吗",conversation_id=None,use_dify=True,on_text=seen.append))
    assert len(calls)==1 and result["source"]=="dify"
    assert seen[0]=="我在听。" and result["reply"].endswith("哪件事？")

@pytest.mark.parametrize("query",["我要请假","我想请个假","我的申请进度","我的资料"])
def test_clear_menu_and_official_records_never_wait_for_planning(db, monkeypatch,query):
    prepare_turn(monkeypatch)
    fail_model(monkeypatch)
    result=asyncio.run(workspace.run_turn(db,student_id=2,query=query,conversation_id=None,use_dify=True,on_text=lambda _:None))
    assert result["intent"] not in ("chat","support")

def test_business_extraction_is_readonly_and_bounded(db,monkeypatch):
    prepare_turn(monkeypatch)
    calls=[]
    async def plan(**kwargs):
        calls.append(kwargs)
        assert kwargs["overall_timeout"]==5
        return AssistantUnderstanding(intent="leave_create",fields={"reason":"身体不适"})
    async def no_visible(**kwargs):pytest.fail("Business drafts cannot use the visible model")
    monkeypatch.setattr(assistant_dify,"understand",plan)
    monkeypatch.setattr(assistant_dify,"stream_reply",no_visible)
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="病假，2026-12-04 09:00到2026-12-04 18:00，身体不适",conversation_id=None,use_dify=True,on_text=lambda _:None))
    assert len(calls)==1 and result["task"]["status"]=="awaiting_confirmation"

def test_model_deadline_reports_unfinished_without_uncertified_partial_or_template(db,monkeypatch):
    prepare_turn(monkeypatch)
    async def no_plan(**kwargs):pytest.fail("No planning for a clear support question")
    calls=[]
    async def timed_out(**kwargs):
        calls.append(kwargs)
        assert kwargs["first_content_timeout"]==12 and 0 < kwargs["overall_timeout"]<=15
        kwargs["on_text"]("我在听。")
        raise BusinessError(504,"首段内容等待超时")
    monkeypatch.setattr(assistant_dify,"understand",no_plan)
    monkeypatch.setattr(assistant_dify,"stream_reply",timed_out)
    seen=[]
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="最近有点想家",conversation_id=None,use_dify=True,on_text=seen.append))
    assert result["source"]=="local_fallback" and "" not in seen
    assert len(calls)==1 and "未能完成" in result["reply"]
    assert result["reply_notice"]=="回复中断，请重试"
    assert result["task"] is None and seen[-1]==result["reply"]


def test_request_to_talk_about_study_fatigue_is_support_not_public_faq(db,monkeypatch):
    prepare_turn(monkeypatch)
    async def no_plan(**kwargs):pytest.fail("A request to talk needs no model planning")
    async def reply(**kwargs):
        assert kwargs["kind"]=="support"
        return "我在听。最近最累的是课程安排，还是一直没有休息好？"
    def no_knowledge(*args,**kwargs):pytest.fail("Do not answer a request for conversation with a study FAQ")
    monkeypatch.setattr(assistant_dify,"understand",no_plan)
    monkeypatch.setattr(assistant_dify,"stream_reply",reply)
    monkeypatch.setattr(workspace.knowledge,"answer",no_knowledge)
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="最近学习有点累，我想找个人聊聊。",conversation_id=None,use_dify=True,on_text=lambda _:None))
    assert result["intent"]=="support" and result["source"]=="dify" and not result.get("task")
