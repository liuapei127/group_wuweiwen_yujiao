"""V5 regressions: follow-up context, direct relevance and requested brevity."""
import pytest
from app.modules.student import assistant_knowledge as knowledge
from tests.modules.test_student_experience import knowledge_db

HISTORY = [{"role": "user", "content": "我在新加坡，想坐公交，怎么坐？"},
           {"role": "assistant", "content": "审核的公交说明"}]

@pytest.mark.parametrize("country,first", [("Singapore", "我在新加坡，想坐公交，怎么坐？"),
                                           ("Germany", "德国公交怎么坐？")])
def test_payment_followup_uses_the_current_transport_subject(knowledge_db, country, first):
    history = [{"role": "user", "content": first}]
    result = knowledge.answer(knowledge_db, country, "那怎么付钱？", history=history)
    assert result["knowledge_keys"][0] == country + "/transport/" + ("0" if country == "Singapore" else "1")
    assert "没有查到" not in result["reply"]

def test_registration_followup_has_reviewed_answer(knowledge_db):
    result = knowledge.answer(knowledge_db, "Singapore", "那需要注册吗？", history=HISTORY)
    assert result["knowledge_keys"][0] == "Singapore/transport/0"
    assert "不必" in result["reply"] and "注册" in result["reply"]

def test_bus_question_does_not_append_train_instructions(knowledge_db):
    result = knowledge.answer(knowledge_db, "Singapore", "我在新加坡，想坐公交，怎么坐？")
    assert result["knowledge_keys"] == ["Singapore/transport/4"]
    assert "MRT" not in result["reply"] and "地铁" not in result["reply"]
    assert len(result["cards"]) == 1

@pytest.mark.parametrize("country", ["Germany", "Singapore"])
def test_one_sentence_request_is_short_and_stays_on_subject(knowledge_db, country):
    result = knowledge.answer(knowledge_db, country, "只用一句话告诉我，公交怎么坐？")
    assert len(result["reply"]) <= 100
    assert "\n" not in result["reply"]
    assert "MRT" not in result["reply"]

def test_format_followup_keeps_the_same_subject(knowledge_db):
    result = knowledge.answer(knowledge_db, "Singapore", "能简单一点吗？", history=HISTORY)
    assert result["knowledge_keys"] == ["Singapore/transport/4"]
    assert len(result["reply"]) <= 100

def test_new_explicit_topic_does_not_inherit_old_transport(knowledge_db):
    result = knowledge.answer(knowledge_db, "Singapore", "租房先看什么？", history=HISTORY)
    assert all(key.startswith("Singapore/housing/") for key in result["knowledge_keys"])

def test_business_switch_breaks_knowledge_context():
    history = HISTORY + [{"role": "user", "content": "我要请假"}]
    resolved = knowledge.resolve_question("那要准备什么？", history)
    assert not resolved["contextual"]
    assert resolved["category"] is None

def test_model_expansion_cannot_invent_a_followup_subject(knowledge_db):
    result = knowledge.answer(knowledge_db, "Singapore", "那怎么付钱？ 公交 银行卡",
                              original_query="那怎么付钱？", history=[])
    assert not result.get("knowledge_keys")

def test_two_explicit_transport_objects_can_be_answered_without_duplicate_blocks(knowledge_db):
    result = knowledge.answer(knowledge_db, "Singapore", "公交和地铁分别怎么坐？")
    assert set(result["knowledge_keys"]) == {"Singapore/transport/4", "Singapore/transport/3"}
    assert len(result["cards"]) == 1
    assert len(result["reply"]) <= 260

def test_detailed_followup_recovers_reviewed_full_content(knowledge_db):
    history = [{"role": "user", "content": "新加坡地铁怎么坐？"}]
    result = knowledge.answer(knowledge_db, "Singapore", "详细说说每一步", history=history)
    assert result["knowledge_keys"][0] == "Singapore/transport/3"
    assert "进站" in result["reply"] and "出站" in result["reply"] and "同一" in result["reply"]


def test_plain_country_selection_is_preserved_for_followups(knowledge_db):
    history = [{"role": "user", "content": "公交怎么坐？"},
               {"role": "assistant", "content": "德国还是新加坡？"},
               {"role": "user", "content": "新加坡"}]
    assert knowledge.country_for("那怎么付钱？", {"abroad_country": "Germany"}, history) == "Singapore"
    resolved = knowledge.resolve_question("那怎么付钱？", history)
    assert resolved["query"].startswith("新加坡公交")
    result = knowledge.answer(knowledge_db, "Singapore", "那怎么付钱？", history=history)
    assert result["knowledge_keys"] == ["Singapore/transport/0"]


def test_only_student_words_resolve_a_public_followup():
    history = [{"role": "assistant", "content": "新加坡公交可以这样坐"}]
    assert not knowledge.resolve_question("那怎么付钱？", history)["contextual"]


def test_cross_country_followup_preserves_topic_without_claiming_location():
    history = [{"role": "user", "content": "德国公交怎么坐？"}]
    resolved = knowledge.resolve_question("新加坡呢？", history)
    assert resolved["contextual"] and resolved["country"] == "Singapore"
    assert resolved["subject"] == "公交"


def test_social_switch_does_not_reuse_older_public_topic():
    history = HISTORY + [{"role": "user", "content": "我最近有点想家"}]
    assert not knowledge.resolve_question("能简单一点吗？", history)["contextual"]


def test_country_only_followup_does_not_reuse_business_topic():
    history = [{"role": "user", "content": "我要请假"}]
    assert not knowledge.resolve_question("新加坡呢？", history)["contextual"]


def test_format_followup_preserves_the_last_payment_facet(knowledge_db):
    history = HISTORY + [{"role": "user", "content": "那怎么付钱？"}]
    result = knowledge.answer(knowledge_db, "Singapore", "简单一点", history=history)
    assert result["knowledge_keys"] == ["Singapore/transport/0"]


def test_catalog_short_forms_are_reviewed_bounded_and_keep_full_detail():
    import json
    from pathlib import Path
    rows = json.loads((Path(__file__).parents[2] / "docs/student-workspace/overseas-life-catalog.json").read_text(encoding="utf-8"))
    for row in rows:
        assert len(row["details"]["faqs"]) == 6
        for faq in row["details"]["faqs"]:
            assert 0 < len(faq["short_answer"]) <= 100
            assert faq["answer"] and faq["source_url"].startswith("https://")
    medical = next(row for row in rows if row["country"] == "Germany" and row["category"] == "medical")["details"]["faqs"][3]
    assert all(word in medical["short_answer"] for word in ("非危及生命", "116117", "德语", "112"))


@pytest.mark.parametrize("selection", ["德国", "德国呢"])
def test_latest_country_selection_overrides_the_older_topic_country(selection):
    history = [{"role": "user", "content": "新加坡公交怎么坐？"},
               {"role": "user", "content": selection}]
    resolved = knowledge.resolve_question("那怎么付钱？", history)
    assert resolved["country"] == "Germany" and resolved["subject"] == "公交"
    assert knowledge.country_for("那怎么付钱？", {"abroad_country": "Singapore"}, history) == "Germany"


def test_linked_subject_change_keeps_country_but_changes_subject(knowledge_db):
    history = [{"role": "user", "content": "新加坡公交怎么坐？"}]
    resolved = knowledge.resolve_question("那地铁怎么坐？", history)
    assert resolved["contextual"] and resolved["country"] == "Singapore"
    assert resolved["subject"] == "地铁"
    country = knowledge.country_for("那地铁怎么坐？", {"abroad_country": "Germany"}, history)
    result = knowledge.answer(knowledge_db, country, "那地铁怎么坐？", history=history)
    assert result["knowledge_keys"] == ["Singapore/transport/3"]


def test_independent_subject_question_uses_profile_country():
    history = [{"role": "user", "content": "新加坡公交怎么坐？"}]
    assert knowledge.country_for("地铁怎么坐？", {"abroad_country": "Germany"}, history) == "Germany"


@pytest.mark.parametrize("first,next_country,expected", [
    ("新加坡公交怎么坐？", "德国", "Germany"),
    ("德国公交怎么坐？", "新加坡", "Singapore"),
])
def test_country_in_elliptical_facet_precedes_the_older_country(first, next_country, expected):
    history = [{"role": "user", "content": first},
               {"role": "user", "content": next_country + "怎么付钱？"}]
    resolved = knowledge.resolve_question("那需要注册吗？", history)
    assert resolved["country"] == expected and resolved["subject"] == "公交"
    assert resolved["query"].startswith(next_country + "公交")
    assert knowledge.country_for("那需要注册吗？", {}, history) == expected
