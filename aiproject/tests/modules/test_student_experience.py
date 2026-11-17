"""Conversation intent, source-grounded answers and DE/SG content parity."""
import asyncio,json
from pathlib import Path
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine,text,select
from sqlalchemy.orm import Session
from pydantic import SecretStr
from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.modules.student import assistant_knowledge as knowledge,assistant_guidance as guidance,assistant_workspace as workspace
from app.modules.student import assistant_dify,assistant_store,assistant_context
from app.modules.student.schemas import AssistantUnderstanding,KnowledgeRetrievalRequest
from app.modules.student.models import StudentAssistantTask
from tests.modules.test_student_workspace import db,prepare_turn,cid,leave

CATALOG=json.loads((Path(__file__).parents[2]/"docs/student-workspace/overseas-life-catalog.json").read_text(encoding="utf-8"))

@pytest.fixture
def knowledge_db():
    engine=create_engine("sqlite://")
    with Session(engine) as db:
        db.execute(text("CREATE TABLE overseas_life_knowledge(id INTEGER PRIMARY KEY,country TEXT,category TEXT,title TEXT,content TEXT,status INTEGER,city TEXT,source_title TEXT,source_url TEXT,verified_at DATE,update_time DATETIME,details JSON)"))
        for index,row in enumerate(CATALOG):
            db.execute(text("INSERT INTO overseas_life_knowledge VALUES(:id,:country,:category,:title,:content,1,NULL,:source_title,:source_url,'2026-11-16',NULL,:details)"),{**row,"id":index+1,"details":json.dumps(row["details"],ensure_ascii=False)})
        db.commit()
        yield db
    engine.dispose()

@pytest.mark.parametrize("row,faq",[(row,faq) for row in CATALOG for faq in row["details"]["faqs"]],ids=[row["country"]+"-"+row["category"]+"-"+str(i) for row in CATALOG for i,_ in enumerate(row["details"]["faqs"])])
def test_reviewed_questions_are_retrievable_in_their_own_country(knowledge_db,row,faq):
    found=knowledge.retrieve(knowledge_db,row["country"],faq["question"],3)
    assert found and any(result["answer"]==faq["answer"] for result in found)
    assert all(result["country"]==row["country"] for result in found)
    assert all(result["source_url"].startswith("https://") for result in found)


def test_country_parity_and_sources():
    categories={"arrival","medical","transport","housing","study","emergency"}
    for country in ("Germany","Singapore"):
        assert {r["category"] for r in CATALOG if r["country"]==country}==categories
        assert sum(len(r["details"]["faqs"]) for r in CATALOG if r["country"]==country)==36
    for row in CATALOG:
        assert row["details"]["steps"] and row["details"]["sources"]


def test_search_and_retrieval_include_guides_beyond_the_first_batch(knowledge_db, monkeypatch):
    from app.modules.student import service
    monkeypatch.setattr(get_settings(), "stu_assistant_mode", "workspace")
    for index in range(20, 83):
        details = {"faqs": [{"question": "验收关键字如何查询", "answer": "后续批次资料",
                             "keywords": ["验收关键字"]}]} if index >= 81 else {}
        knowledge_db.execute(text("""INSERT INTO overseas_life_knowledge
            (id,country,category,title,content,status,details,source_title,source_url)
            VALUES (:id,'Germany','study','较早的资料','正文',1,:details,'官方入口','https://example.invalid/source')"""),
            {"id": index, "details": json.dumps(details, ensure_ascii=False)})
    knowledge_db.commit()
    page = service.overseas_resources(knowledge_db, 2, "验收关键字", 0, 1, country="Germany")
    assert [row["id"] for row in page["items"]] == [81] and page["next_after_id"] == 81
    next_page = service.overseas_resources(knowledge_db, 2, "验收关键字", 81, 1, country="Germany")
    assert [row["id"] for row in next_page["items"]] == [82] and next_page["next_after_id"] is None
    assert any(row["answer"] == "后续批次资料" for row in knowledge.retrieve(knowledge_db, "Germany", "验收关键字"))


def test_police_phone_answers_do_not_cross_countries(knowledge_db):
    de=knowledge.answer(knowledge_db,"Germany","报警电话是多少")
    sg=knowledge.answer(knowledge_db,"Singapore","报警电话是多少")
    assert "110" in de["reply"] and "999" not in de["reply"]
    assert "999" in sg["reply"] and "110" not in sg["reply"]
    assert de["cards"][0]["source_url"] and sg["cards"][0]["source_url"]


def test_external_knowledge_authentication_and_probe(knowledge_db,monkeypatch):
    monkeypatch.setattr(get_settings(),"stu_knowledge_token",SecretStr("test-knowledge-secret"))
    body=KnowledgeRetrievalRequest(knowledge_id="Singapore",query="报警电话")
    with pytest.raises(BusinessError):knowledge.external_retrieval(knowledge_db,body,"incorrect")
    results=knowledge.external_retrieval(knowledge_db,body,"test-knowledge-secret")
    assert results["records"] and "999" in results["records"][0]["content"]
    assert knowledge.external_retrieval(knowledge_db,KnowledgeRetrievalRequest(knowledge_id=""),"test-knowledge-secret")=={"records":[]}


def test_unknown_country_and_unsupported_question_do_not_invent_answers(knowledge_db):
    assert knowledge.answer(knowledge_db,None,"报警电话")["choices"]
    answer=knowledge.answer(knowledge_db,"Germany","学院内部奖学金审核口令")
    assert not answer.get("cards") and "没有查到可靠答案" in answer["reply"]
    assert knowledge.country_for("新加坡怎么坐地铁",{"abroad_country":"Germany"})=="Singapore"
    assert knowledge.country_for("德国和新加坡的报警电话",{"abroad_country":"Germany"}) is None


@pytest.mark.parametrize("query",["我们学校环境太差了","我有点想家","我想回家","我只是想找人说说话"])
def test_feelings_do_not_create_a_business_task(db,monkeypatch,query):
    prepare_turn(monkeypatch)
    result=asyncio.run(workspace.run_turn(db,student_id=2,query=query,conversation_id=None,use_dify=False))
    assert result["intent"] in ("support","chat") and result.get("task") is None
    assert db.scalars(select(StudentAssistantTask)).all()==[]


def test_ordinary_greeting_cannot_use_model_routing_to_start_a_complaint(db,monkeypatch):
    prepare_turn(monkeypatch)
    async def plan(**_):
        pytest.fail("A greeting cannot ask the planning model to open a business task")
    async def reply(**_):
        return "你好呀，想先聊什么？"
    monkeypatch.setattr(assistant_dify,"understand",plan)
    monkeypatch.setattr(assistant_dify,"stream_reply",reply)
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="你好",conversation_id=None,use_dify=True))
    assert result["intent"]=="chat" and not result.get("task")


def test_guide_collects_one_step_at_a_time_and_preserves_real_reason(db,monkeypatch):
    prepare_turn(monkeypatch)
    a=asyncio.run(workspace.run_turn(db,student_id=2,query="我要请假",conversation_id=None,use_dify=False))
    assert a["task"]["guide"]["kind"]=="choice" and len(a["task"]["guide"]["choices"])==3
    cid=a["conversation_id"]
    b=asyncio.run(workspace.run_turn(db,student_id=2,query="病假",conversation_id=cid,use_dify=False))
    assert b["task"]["guide"]["kind"]=="datetime"
    c=asyncio.run(workspace.run_turn(db,student_id=2,query="2026-12-20 09:30 到 2026-12-20 17:00",conversation_id=cid,use_dify=False))
    assert c["task"]["guide"]["field"]=="reason"
    d=asyncio.run(workspace.run_turn(db,student_id=2,query="事由：去医院复查",conversation_id=cid,use_dify=False))
    assert d["task"]["status"]=="awaiting_confirmation" and d["task"]["form_values"]["reason"]=="去医院复查"
    edited=asyncio.run(workspace.run_turn(db,student_id=2,query="我要修改请假时间",conversation_id=cid,use_dify=False))
    assert edited["task"]["guide"]["kind"]=="datetime" and edited["task"]["form_values"]["reason"]=="去医院复查"


def test_rich_reply_survives_history_reload(db,monkeypatch):
    prepare_turn(monkeypatch)
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="学校环境太差了",conversation_id=None,use_dify=False))
    saved=assistant_store.list_messages(db,result["conversation_id"])[-1]
    assert saved["presentation"]["choices"]==result["choices"]


def test_public_phone_claims_and_fake_actions_are_rejected_in_social_replies():
    assert guidance.safe_social_reply("已经帮你联系老师了") is None
    assert guidance.safe_social_reply("我也可以帮你联系学校的支持资源") is None
    assert guidance.safe_social_reply("我可以帮你联系老师") is None
    assert guidance.safe_social_reply("老师电话是13912345678") is None
    assert guidance.safe_social_reply("你愿意说说最困扰你的事情吗？")


def test_feedback_context_is_a_suggestion_until_student_supplies_details(db,monkeypatch):
    prepare_turn(monkeypatch)
    first=asyncio.run(workspace.run_turn(db,student_id=2,query="我们学校环境太差了",conversation_id=None,use_dify=False))
    next_turn=asyncio.run(workspace.run_turn(db,student_id=2,query="帮我准备反馈",conversation_id=first["conversation_id"],use_dify=False))
    assert not next_turn["task"]["form_values"]["content"]
    assert next_turn["task"]["status"]=="collecting"
    assert db.get(StudentAssistantTask,next_turn["task"]["id"]).payload["_context"]=="我们学校环境太差了"


def test_plain_medical_information_is_not_a_leave_request(db,monkeypatch):
    prepare_turn(monkeypatch)
    monkeypatch.setattr(knowledge,"answer",lambda *_, **__:{"reply":"已核对的就医信息","intent":"ask"})
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="我想去医院",conversation_id=None,use_dify=False))
    assert result["intent"]=="ask" and not result["task"]


def test_country_choice_resolves_an_initial_two_country_question():
    assert knowledge.country_for("德国：德国和新加坡报警电话是多少",{"abroad_country":"Singapore"})=="Germany"
    assert knowledge.country_for("新加坡：德国和新加坡报警电话是多少",{"abroad_country":"Germany"})=="Singapore"


def test_safe_model_companion_reply_is_used_without_creating_tasks(db,monkeypatch):
    prepare_turn(monkeypatch)
    async def reply(**_):
        return "最近哪一件小事最让你想家？可以慢慢说。"
    monkeypatch.setattr(assistant_dify,"stream_reply",reply)
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="我最近有点想家",conversation_id=None,use_dify=True))
    assert "哪一件小事" in result["reply"] and result["choices"] and not result.get("task")


def test_negated_feedback_is_not_an_explicit_request():
    assert not guidance.explicit_feedback("我不希望投诉，只想说说")
    assert not guidance.explicit_feedback("我不是要投诉")
    assert guidance.explicit_feedback("帮我准备反馈")


def test_student_can_stop_a_pending_feedback_request(db,monkeypatch):
    prepare_turn(monkeypatch)
    first=asyncio.run(workspace.run_turn(db,student_id=2,query="我要投诉",conversation_id=None,use_dify=False))
    result=asyncio.run(workspace.run_turn(db,student_id=2,query="我不想投诉了",conversation_id=first["conversation_id"],use_dify=False))
    assert result["task"]["status"]=="cancelled"


def test_feedback_result_keeps_suggestion_type():
    from datetime import datetime
    from app.modules.feedback.schemas import StudentComplaintOut
    result=StudentComplaintOut.model_validate({"id":1,"ticket_type":"suggestion","category":"learning","title":None,"content":"希望增加课后答疑时间","status":"pending","solution":None,"create_time":datetime(2026,11,16),"update_time":datetime(2026,11,16)})
    assert result.model_dump()["ticket_type"]=="suggestion"


def test_student_feedback_list_includes_owned_suggestions_without_other_students(db):
    from datetime import datetime
    from sqlalchemy import insert
    from app.modules.feedback.models import student_feedback_ticket
    from app.modules.feedback.repository import FeedbackRepository
    student_feedback_ticket.create(db.get_bind())
    now=datetime(2026,11,16)
    for id,kind,owner in ((1,"complaint",2),(2,"suggestion",2),(3,"suggestion",3),(4,"consult",2)):
        db.execute(insert(student_feedback_ticket).values(id=id,ticket_type=kind,student_id=owner,category="learning",content="已核对的学生反馈",status="pending",priority="medium",assignee_id=4,is_notified=0,create_time=now,update_time=now))
    db.commit()
    repo=FeedbackRepository(db)
    assert [row["id"] for row in repo.list_student_complaints(2,None,20)]==[2,1]
    assert repo.get_student_complaint(2,2)["ticket_type"]=="suggestion"
    assert repo.get_student_complaint(3,2) is None
