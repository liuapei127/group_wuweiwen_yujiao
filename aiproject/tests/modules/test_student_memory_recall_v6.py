"""Per-account durable recall, not a summary of every chat turn."""
import json
from datetime import datetime, timedelta
import pytest
from sqlalchemy import select
from app.modules.student.models import StuMem0Memory
from app.modules.student import assistant_mem0 as memory, memory_service
from tests.modules.test_student_memory_management import memory_db, remember

def insert(db,text,metadata=None,sid=2,days=0):
    now=datetime(2026,11,17)+timedelta(days=days)
    row=StuMem0Memory(user_id=f"stu_{sid}",memory=text,metadata_json=json.dumps(metadata or {},ensure_ascii=False),create_time=now,update_time=now)
    db.add(row);db.commit();return row

def test_name_and_response_preference_are_recalled_together_across_conversations(memory_db):
    remember(memory_db,2,"我叫小明")
    remember(memory_db,2,"我更喜欢简短的回答")
    recalled=memory.search_memories(memory_db,student_id=2,query="你好，可以陪我聊聊吗")
    assert "学生姓名：小明" in recalled
    assert any("简短" in x for x in recalled)

def test_chinese_preference_question_is_not_crowded_out_by_name(memory_db):
    remember(memory_db,2,"我叫小明")
    remember(memory_db,2,"以后请用清单回答")
    recalled=memory.search_memories(memory_db,student_id=2,query="我更喜欢什么样的回答方式")
    assert any("清单" in x for x in recalled)

def test_old_name_and_preference_survive_more_than_eighty_legacy_questions(memory_db):
    insert(memory_db,"学生姓名：小明",{"kind":"name"})
    insert(memory_db,"学生自述：我喜欢简短回答",{"kind":"preference"})
    for n in range(90):insert(memory_db,"学生说：查一下我的申请进度"+str(n),days=1)
    recalled=memory.search_memories(memory_db,student_id=2,query="我叫什么")
    assert "学生姓名：小明" in recalled and any("简短" in x for x in recalled)
    assert not any("申请进度" in x for x in recalled)

def test_accounts_cannot_share_name_preference_or_self_reports(memory_db):
    remember(memory_db,2,"我叫小明");remember(memory_db,2,"我喜欢简短回答")
    remember(memory_db,3,"我叫小李");remember(memory_db,3,"我喜欢详细回答")
    first=memory.search_memories(memory_db,student_id=2,query="回答偏好")
    second=memory.search_memories(memory_db,student_id=3,query="回答偏好")
    assert all("小李" not in x and "详细" not in x for x in first)
    assert all("小明" not in x and "简短" not in x for x in second)

def test_old_questions_are_visible_in_manager_but_not_recalled(memory_db):
    records=["学生说：马云是谁；助手：马云是企业家", "学生说：我的申请到哪里了", "学生说：我要去医院", "学生说：怎么付钱"]
    for line in records:insert(memory_db,line)
    assert memory.search_memories(memory_db,student_id=2,query="申请进度怎么付钱") == []
    assert {r["memory"] for r in memory_service.listing(memory_db,2)["items"]} == set(records)

def test_legacy_self_report_is_only_used_for_a_related_question(memory_db):
    insert(memory_db,"学生说：我想家；助手：你刚到德国")
    assert memory.search_memories(memory_db,student_id=2,query="想家") == ["学生说：我想家"]
    assert memory.search_memories(memory_db,student_id=2,query="你好") == []

def test_corrected_preference_keeps_kind_and_is_recalled_with_name(memory_db):
    remember(memory_db,2,"我叫小明");remember(memory_db,2,"我喜欢详细回答")
    row=next(x for x in memory_service.listing(memory_db,2)["items"] if x["kind"]=="preference")
    corrected=memory_service.correct(memory_db,2,row["id"],"我更喜欢简短回答",row["version"])
    assert corrected["kind"]=="preference"
    recalled=memory.search_memories(memory_db,student_id=2,query="回答方式")
    assert any("简短" in x for x in recalled) and not any("详细" in x for x in recalled)

def test_delete_removes_recall_without_deleting_other_account_or_history(memory_db):
    remember(memory_db,2,"我叫小明");remember(memory_db,2,"我喜欢简短回答");remember(memory_db,3,"我喜欢详细回答")
    row=next(x for x in memory_service.listing(memory_db,2)["items"] if x["kind"]=="preference")
    memory_service.erase(memory_db,2,row["id"],row["version"])
    assert not any("简短" in x for x in memory.search_memories(memory_db,student_id=2,query="回答方式"))
    assert len(memory_service.listing(memory_db,3)["items"])==1

@pytest.mark.parametrize("query",["马云是谁","马云是谁？","请记住，马云是谁？","老师叫我去办公室","我叫什么名字？"])
def test_questions_and_third_person_instructions_do_not_become_student_facts(query):
    assert memory._compact_fact(query,"马云是企业家。") == ""

@pytest.mark.parametrize("query",["请记住，我的密码是Secret123","请记住我的身份证号码是123456789012345678","请记住，我想自杀","请记住我的API_KEY是secret-token"])
def test_credentials_and_high_risk_content_are_not_saved_as_long_term_facts(query):
    assert memory._compact_fact(query,"我在听。") == ""

def test_latest_conflicting_reply_length_preference_wins_without_erasing_history(memory_db):
    insert(memory_db,"学生自述：我喜欢详细回答",{"kind":"preference"},days=0)
    insert(memory_db,"学生自述：我更喜欢简短回答",{"kind":"preference"},days=1)
    recalled=memory.search_memories(memory_db,student_id=2,query="回答方式")
    assert any("简短" in x for x in recalled) and not any("详细" in x for x in recalled)
    assert len(memory_service.listing(memory_db,2)["items"])==2


@pytest.mark.parametrize("query", ["我喜欢什么？", "我希望你告诉我马云是谁", "以后请帮我查询申请进度"])
def test_preference_shaped_questions_and_business_requests_are_not_facts(query):
    assert memory._compact_fact(query, "好的。") == ""


def test_name_is_not_lost_behind_many_preference_rows(memory_db):
    insert(memory_db, "学生姓名：小明", {"kind": "name"})
    for n in range(90):
        insert(memory_db, "学生自述：我喜欢食物" + str(n), {"kind": "preference"}, days=1)
    assert "学生姓名：小明" in memory.search_memories(memory_db, student_id=2, query="你好")


def test_correction_blocks_inflight_old_fact_rewrite(memory_db):
    remember(memory_db, 2, "我喜欢详细回答")
    record = memory_service.listing(memory_db, 2)["items"][0]
    memory.search_memories(memory_db, student_id=2, query="回答方式")
    memory_service.correct(memory_db, 2, record["id"], "我更喜欢简短回答", record["version"])
    memory.remember_turn(memory_db, student_id=2, user_text="我喜欢详细回答", assistant_text="好的", conversation_id="old")
    recalled = memory.search_memories(memory_db, student_id=2, query="回答方式")
    assert any("简短" in text for text in recalled)
    assert not any("详细" in text for text in recalled)


def test_correct_rejects_credentials_without_changing_stored_fact(memory_db):
    from app.core.exceptions import BusinessError
    remember(memory_db, 2, "我喜欢简短回答")
    record = memory_service.listing(memory_db, 2)["items"][0]
    with pytest.raises(BusinessError) as error:
        memory_service.correct(memory_db, 2, record["id"], "我的密码是Secret123", record["version"])
    assert error.value.status_code == 422
    assert memory_service.listing(memory_db, 2)["items"][0]["memory"] == record["memory"]



def test_repeated_explicit_preference_becomes_latest_without_duplicate_rows(memory_db):
    remember(memory_db, 2, "我喜欢详细回答")
    first = memory_service.listing(memory_db, 2)["items"][0]
    remember(memory_db, 2, "我更喜欢简短回答")
    remember(memory_db, 2, "我喜欢详细回答")
    recalled = memory.search_memories(memory_db, student_id=2, query="回答方式")
    assert any("详细" in text for text in recalled)
    assert not any("简短" in text for text in recalled)
    records = memory_service.listing(memory_db, 2)["items"]
    assert len(records) == 2
    current = next(row for row in records if row["id"] == first["id"])
    assert current["version"] != first["version"]
    from app.core.exceptions import BusinessError
    with pytest.raises(BusinessError) as error:
        memory_service.correct(memory_db, 2, first["id"], "我喜欢清单回答", first["version"])
    assert error.value.status_code == 409



@pytest.mark.parametrize("label", ["password", "PASSWORD", "passwd", "pwd", "passcode", "otp"])
def test_english_credentials_are_not_saved_or_corrected_into_memory(memory_db, label):
    from app.core.exceptions import BusinessError
    text = "请记住，我的" + label + "是DemoSecret"
    assert memory._compact_fact(text, "好的。") == ""
    remember(memory_db, 2, "我喜欢简短回答")
    row = memory_service.listing(memory_db, 2)["items"][0]
    with pytest.raises(BusinessError) as error:
        memory_service.correct(memory_db, 2, row["id"], text, row["version"])
    assert error.value.status_code == 422


def test_correcting_older_preference_makes_it_latest(memory_db):
    remember(memory_db, 2, "我喜欢详细回答")
    first = memory_service.listing(memory_db, 2)["items"][0]
    remember(memory_db, 2, "我更喜欢简短回答")
    memory_service.correct(memory_db, 2, first["id"], "我喜欢详尽回答", first["version"])
    recalled = memory.search_memories(memory_db, student_id=2, query="回答方式")
    assert any("详尽" in text for text in recalled)
    assert not any("简短" in text for text in recalled)
