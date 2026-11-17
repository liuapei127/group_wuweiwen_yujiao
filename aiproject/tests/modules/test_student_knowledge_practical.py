"""Real student questions must produce usable, country-scoped public information."""
import json
from pathlib import Path

import pytest

from app.modules.student import assistant_knowledge as knowledge
from tests.modules.test_student_experience import knowledge_db


@pytest.mark.parametrize("country,query,key,required", [
    ("Singapore", "我要做地铁", "Singapore/transport/3", ("银行卡", "换乘", "进站", "出站", "同一")),
    ("Singapore", "坐地铁前一定要注册账号吗", "Singapore/transport/0", ("不必", "SimplyGo")),
    ("Singapore", "我想坐巴士", "Singapore/transport/4", ("下车铃", "同一卡片", "感应")),
    ("Singapore", "地铁进出站能换手机吗", "Singapore/transport/1", ("同一", "不要")),
    ("Singapore", "地铁扣费多了怎么退款", "Singapore/transport/5", ("SimplyGo", "核查")),
    ("Germany", "我要坐地铁", "Germany/transport/3", ("车票", "激活", "查验", "城市")),
    ("Germany", "德国票可以坐ICE吗", "Germany/transport/4", ("不普遍适用", "ICE")),
    ("Germany", "我要去医院", "Germany/medical/3", ("全科", "预约", "到诊", "116117", "112")),
    ("Singapore", "我想去医院", "Singapore/medical/3", ("GP", "预约", "证件", "995")),
    ("Germany", "周末晚上想看病", "Germany/medical/2", ("116117", "德语", "112")),
    ("Germany", "我看病保险能报销吗", "Germany/medical/1", ("不能保证", "保险")),
    ("Singapore", "去医院门诊要带什么", "Singapore/medical/4", ("SGH", "不代表所有诊所")),
    ("Singapore", "不会安全通话怎么短信报警", "Singapore/emergency/3", ("70999", "位置")),
    ("Singapore", "租房中介的身份怎么核实", "Singapore/housing/3", ("CEA", "电话号码")),
    ("Germany", "入住后住址登记需要哪些材料", "Germany/arrival/2", ("身份证件", "Wohnungsgeberbestätigung")),
])
def test_practical_questions_select_relevant_workflow(knowledge_db, country, query, key, required):
    result = knowledge.answer(knowledge_db, country, query)
    assert result["knowledge_keys"][0] == key
    assert all(phrase in result["reply"] for phrase in required)
    assert result["cards"] and all(card["source_url"].startswith("https://") for card in result["cards"])
    assert "德国还是新加坡" not in result["reply"]


def test_known_destination_is_default_even_after_an_old_comparison():
    history = [{"role": "user", "content": "新加坡的地铁和德国有区别吗"},
               {"role": "user", "content": "新加坡图书馆能借书吗"}]
    assert knowledge.country_for("我要坐地铁", {"abroad_country": "Germany"}, history) == "Germany"
    assert knowledge.country_for("我要去医院", {"abroad_country": "Singapore"}) == "Singapore"
    assert knowledge.country_for("我要坐地铁", {"abroad_country": "Germany"},
                                 [{"role": "user", "content": "我现在在新加坡"}]) == "Singapore"
    assert knowledge.country_for("在新加坡怎么坐地铁", {"abroad_country": "Germany"}) == "Singapore"
    assert knowledge.country_for("Germany and Singapore", {"abroad_country": "Germany"}) is None


def test_search_expansion_cannot_turn_hospital_question_into_insurance(knowledge_db):
    result = knowledge.answer(knowledge_db, "Germany", "去医院 保险 报销 理赔 费用",
                              ["Germany/medical/1"], original_query="我要去医院")
    assert result["knowledge_keys"][0] == "Germany/medical/3"
    assert "预约" in result["reply"] and "到诊" in result["reply"]
    assert "不能保证" not in result["reply"]


def test_comprehensive_transport_answer_does_not_append_duplicate_facets(knowledge_db):
    result = knowledge.answer(knowledge_db, "Singapore", "第一次坐地铁怎么坐，怎么支付，要查什么路线")
    assert result["knowledge_keys"][0] == "Singapore/transport/3"
    assert result["knowledge_keys"] == ["Singapore/transport/3"]
    assert len(result["cards"]) == 1
    assert all(word in result["reply"] for word in ("银行卡", "路线", "换乘", "进站", "出站"))
    assert result["facts_kind"] == "public_knowledge"


def test_reply_facts_are_reviewed_text_with_sources(knowledge_db):
    catalog = json.loads((Path(__file__).parents[2] / "docs/student-workspace/overseas-life-catalog.json").read_text(encoding="utf8"))
    for country, query in (("Germany", "报警和急救电话"), ("Singapore", "第一次坐地铁怎么坐，怎么支付")):
        result = knowledge.answer(knowledge_db, country, query)
        reviewed = {}
        for article in catalog:
            for index, faq in enumerate(article["details"]["faqs"]):
                reviewed[f"{article['country']}/{article['category']}/{index}"] = faq
        for key, card in zip(result["knowledge_keys"], result["cards"]):
            assert reviewed[key]["short_answer"] in result["reply"]
            assert card["source_url"] == reviewed[key]["source_url"]
            assert key.startswith(country + "/")


def test_country_catalogs_have_matching_categories_and_applicability():
    catalog = json.loads((Path(__file__).parents[2] / "docs/student-workspace/overseas-life-catalog.json").read_text(encoding="utf8"))
    assert len(catalog) == 12
    for row in catalog:
        assert len(row["details"]["faqs"]) == 6
        assert row["verified_at"] == "2026-11-17"
        assert row["details"]["scope"] and row["details"]["sources"]
        assert all(faq["source_title"] and faq["source_url"].startswith("https://") for faq in row["details"]["faqs"])
    sgh = next(row for row in catalog if row["country"] == "Singapore" and row["category"] == "medical")["details"]["faqs"][4]
    assert "SGH" in sgh["scope"]
