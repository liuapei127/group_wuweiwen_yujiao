"""Business boundaries: real durable drafts, ownership/version checks, and semantic fallback."""
import asyncio
from datetime import timedelta
from types import SimpleNamespace
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.core.exceptions import BusinessError
from app.shared.utils.time_util import now_naive
from app.modules.student import assistant_tasks as tasks, assistant_workspace as workspace
from app.modules.student import assistant_store, assistant_mem0, assistant_context, assistant_dify
from app.modules.student.models import StudentAssistantTask, StudentAssistantConversation, StudentAssistantMessage
from app.modules.student.schemas import AssistantUnderstanding


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    for table in (StudentAssistantConversation.__table__, StudentAssistantMessage.__table__, StudentAssistantTask.__table__):
        table.create(engine)
    with Session(engine) as session:
        session.execute(text("CREATE TABLE business_receipt(id INTEGER PRIMARY KEY, owner INTEGER)"))
        session.commit()
        yield session
    engine.dispose()


def cid(db, sid=2):
    return assistant_store.create_conversation(db, sid)["id"]


def leave():
    return {"leave_type": "sick", "start_time": "2026-12-04T09:00:00", "end_time": "2026-12-04T18:00:00", "reason": "身体不适"}


def test_draft_does_not_write_business_and_confirm_replays_once(db, monkeypatch):
    conversation = cid(db)
    draft = tasks.save_draft(db, 2, conversation, "leave", leave(), None)
    assert draft["status"] == "awaiting_confirmation"
    assert db.scalar(text("SELECT COUNT(*) FROM business_receipt")) == 0
    def submit(self, sid, payload, *, commit):
        assert commit is False
        selfdb = db
        selfdb.execute(text("INSERT INTO business_receipt(owner) VALUES (:sid)"), {"sid": sid})
        return SimpleNamespace(model_dump=lambda **_: {"id": 1, "status": "pending"})
    monkeypatch.setattr(tasks.StudentAdminServiceLayer, "submit_student_leave", submit)
    result = tasks.decide(db, 2, draft["id"], draft["version"])
    assert result["status"] == "submitted" and result["result"]["id"] == 1
    assert tasks.decide(db, 2, draft["id"], draft["version"])["result"] == result["result"]
    assert db.scalar(text("SELECT COUNT(*) FROM business_receipt")) == 1


def test_owned_versioned_confirmation_and_cancel(db):
    conversation = cid(db)
    draft = tasks.save_draft(db, 2, conversation, "leave", leave(), None)
    for sid, version in ((3, 1), (2, 77)):
        with pytest.raises(BusinessError):
            tasks.decide(db, sid, draft["id"], version)
        db.rollback()
    changed = tasks.save_draft(db, 2, conversation, "leave", {**leave(), "reason": "家里有事"}, (draft["id"],1))
    assert changed["version"] == 2
    with pytest.raises(BusinessError):
        tasks.decide(db, 2, draft["id"], 1)
    db.rollback()
    assert tasks.decide(db, 2, draft["id"], 2, cancel=True)["status"] == "cancelled"
    with pytest.raises(BusinessError):
        tasks.decide(db, 2, draft["id"], 3)
    db.rollback()
    assert db.scalar(text("SELECT COUNT(*) FROM business_receipt")) == 0


def test_expired_incomplete_and_concurrent_edits_are_blocked(db):
    conversation = cid(db)
    draft = tasks.save_draft(db, 2, conversation, "leave", {}, None)
    with pytest.raises(BusinessError):
        tasks.decide(db, 2, draft["id"], 1)
    db.rollback()
    with pytest.raises(BusinessError):
        tasks.save_draft(db, 2, conversation, "leave", leave(), None)
    row = db.get(StudentAssistantTask, draft["id"])
    row.expires_at = now_naive() - timedelta(seconds=1)
    db.commit()
    with pytest.raises(BusinessError):
        tasks.decide(db, 2, draft["id"], 1)
    assert db.get(StudentAssistantTask, draft["id"]).status == "expired"


def test_business_and_receipt_rollback_together(db, monkeypatch):
    draft = tasks.save_draft(db,2,cid(db),"leave",leave(),None)
    def fail(*args, **kwargs):
        db.execute(text("INSERT INTO business_receipt(owner) VALUES(2)"))
        raise BusinessError(409,"尚未分配有效班主任")
    monkeypatch.setattr(tasks.StudentAdminServiceLayer,"submit_student_leave",fail)
    with pytest.raises(BusinessError):
        tasks.decide(db,2,draft["id"],1)
    assert db.scalar(text("SELECT COUNT(*) FROM business_receipt")) == 0
    assert db.get(StudentAssistantTask,draft["id"]).status == "awaiting_confirmation"


def test_no_invented_time_or_reason_and_time_followup():
    payload, issue = workspace.fill_leave("病假，2026-12-04 到 2026-12-05", {}, {"reason":"身体不适"})
    assert not issue and "reason" not in payload and "start_time" not in payload
    payload, issue = workspace.fill_leave("09:30 到 18:00，事由：身体不适", payload, {})
    assert payload["start_time"] == "2026-12-04T09:30:00"
    assert payload["end_time"] == "2026-12-05T18:00:00"
    payload, issue = workspace.fill_leave("改为25:10到26:00",payload,{})
    assert issue and "start_time" not in payload


def test_explicit_iso_times_and_new_dates_reset_old_times():
    payload, issue = workspace.fill_leave("病假，2026-12-04 09:30 到 2026-12-05 18:00，事由：复查",{}, {})
    assert not issue and payload["start_time"].endswith("09:30:00")
    payload, issue = workspace.fill_leave("改到2026-12-08 到 2026-12-09",payload,{})
    assert "start_time" not in payload


def test_hospital_is_a_query_and_confirm_is_not_inferred():
    assert workspace.local_understanding("我想去医院", None).intent == "ask"
    assert workspace.local_understanding("好的", None).intent != "confirm"
    assert workspace.local_understanding("确认提交", None).intent == "confirm"


def test_feedback_draft_requires_category_type_and_substance():
    payload = workspace.fill_feedback("我要投诉", {}, {"content":"虚构的内容"})
    assert payload == {"ticket_type":"complaint"}
    payload = workspace.fill_feedback("学习相关",payload,{})
    assert "content" not in payload
    payload = workspace.fill_feedback("内容：老师连续三次上课迟到，没有补课",payload,{})
    assert payload["category"] == "learning" and "上课迟到" in payload["content"]
    tasks.validate("feedback", payload)


def prepare_turn(monkeypatch):
    context = {"profile":{"school":"真实院校"}, "applications":[], "deadlines":[], "position":{}, "service_stage":{}, "notes":""}
    monkeypatch.setattr(assistant_context,"snapshot",lambda *_:context)
    monkeypatch.setattr(assistant_mem0,"search_memories",lambda *_,**__:[])
    monkeypatch.setattr(assistant_mem0,"remember_turn",lambda *_,**__:None)


def test_topic_query_keeps_draft_and_model_cannot_confirm(db, monkeypatch):
    prepare_turn(monkeypatch)
    conversation = cid(db)
    draft = tasks.save_draft(db,2,conversation,"leave",leave(),None)
    async def understand(**_):
        return AssistantUnderstanding(intent="confirm",fields={},reply="已提交")
    monkeypatch.setattr(assistant_dify,"understand",understand)
    result = asyncio.run(workspace.run_turn(db,student_id=2,query="好的",conversation_id=conversation,use_dify=True))
    assert result["task"]["status"] == "awaiting_confirmation"
    assert db.scalar(text("SELECT COUNT(*) FROM business_receipt")) == 0
    result = asyncio.run(workspace.run_turn(db,student_id=2,query="我的学校是什么",conversation_id=conversation,use_dify=False))
    assert result["intent"] == "profile" and result["task"]["id"] == draft["id"]


def test_multiple_applications_keep_each_stage():
    rows = [{"id":i,"school":school,"major":"专业","stage_label":stage,"next_action":None,"handler":None,"updated_at":"2026-11-16T09:00:00","source":"员工维护","detail":None} for i,school,stage in ((1,"A大学","审核中"),(2,"B大学","已录取"))]
    result = assistant_context.progress_result({"applications":rows})
    assert len(result["cards"]) == 2 and "不同阶段" in result["reply"]
    assert len(assistant_context.progress_result({"applications":rows},"A大学申请进度")["cards"]) == 1


def test_model_failure_falls_back_without_old_autosubmit(db, monkeypatch):
    prepare_turn(monkeypatch)
    async def failed(**_):
        raise BusinessError(502,"offline")
    monkeypatch.setattr(assistant_dify,"understand",failed)
    result = asyncio.run(workspace.run_turn(db,student_id=2,query="病假，2026-12-04 09:00 到 2026-12-04 18:00，身体不适",conversation_id=None,use_dify=True))
    assert result["source"] == "local_fallback" and result["task"]["status"] == "awaiting_confirmation"
    assert db.scalar(text("SELECT COUNT(*) FROM business_receipt")) == 0


def test_saved_task_is_restored_from_owned_conversation(db, monkeypatch):
    from app.core.config import get_settings
    from app.modules.student.assistant_session import conversation_detail
    monkeypatch.setattr(get_settings(), "stu_assistant_mode", "workspace")
    conversation = cid(db)
    draft = tasks.save_draft(db,2,conversation,"leave",leave(),None)
    db.expire_all()
    assert conversation_detail(db,2,conversation)["task"]["id"] == draft["id"]
    with pytest.raises(BusinessError):
        conversation_detail(db,3,conversation)


def test_leave_kind_alone_cannot_be_the_reason():
    payload, issue = workspace.fill_leave("病假", {}, {"reason":"病假"})
    assert payload == {"leave_type":"sick"} and not issue


def test_overseas_filter_and_sources_are_preserved(db):
    from app.modules.student.repository import life_knowledge
    db.execute(text("CREATE TABLE overseas_life_knowledge(id INTEGER PRIMARY KEY,country TEXT,category TEXT,title TEXT,content TEXT,status INTEGER,city TEXT,source_title TEXT,source_url TEXT,verified_at DATE,update_time DATETIME,details JSON)"))
    db.execute(text("INSERT INTO overseas_life_knowledge VALUES (1,'Germany','medical','医疗入口','已核对',1,NULL,'官方机构','https://example.invalid','2026-11-16',NULL,NULL),(2,'Singapore','medical','其他国家','内容',1,NULL,'官方机构','https://example.invalid','2026-11-16',NULL,NULL),(3,'Germany','transport','交通入口','内容',1,NULL,'官方机构','https://example.invalid','2026-11-16',NULL,NULL),(4,'Germany','medical','停用','内容',0,NULL,'官方机构','https://example.invalid','2026-11-16',NULL,NULL)"))
    rows = life_knowledge(db,("germany",),"",0,10,category="medical",extended=True)
    assert len(rows) == 1 and rows[0]["id"] == 1 and rows[0]["source_title"] == "官方机构"
    assert str(rows[0]["verified_at"]) == "2026-11-16"


def test_workspace_blocks_legacy_writing_callback(db, monkeypatch):
    from app.core.config import get_settings
    from app.modules.student import router
    from app.modules.student.schemas import StudentAssistantRequest
    from starlette.requests import Request
    monkeypatch.setattr(get_settings(),"stu_assistant_mode","workspace")
    monkeypatch.setattr(router,"_student_id",lambda *_,**__:2)
    with pytest.raises(BusinessError, match="草稿确认"):
        asyncio.run(router.student_assistant_run(StudentAssistantRequest(query="我要请假"),Request({"type":"http","client":("127.0.0.1",1)}),db,None))


def test_changing_feedback_category_does_not_replace_the_details():
    old={"ticket_type":"complaint","category":"learning","content":"老师连续三次上课迟到，没有补课"}
    result=workspace.fill_feedback("改为公司相关，其他不变",old,{"content":"改为公司相关，其他不变"})
    assert result["category"]=="company" and result["content"]==old["content"]
    assert workspace.local_understanding("我要提建议",None).intent=="feedback"
