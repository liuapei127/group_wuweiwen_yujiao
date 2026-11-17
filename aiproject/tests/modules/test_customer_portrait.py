from app.modules.profile.customer_import import read_import
from app.modules.profile.portrait import (
    DE_TRAITS, PORTRAIT_KEYS, SG_TRAITS, merge_observations, person_updates, portrait_findings, screening_document,
)


def test_rule_file_attribute_counts():
    assert len({item.group for item in SG_TRAITS}) == 4
    assert len(SG_TRAITS) == 9
    assert len({item.group for item in DE_TRAITS}) == 3
    assert len(DE_TRAITS) == 12


def test_upload_writes_only_attributes_from_the_rule_file():
    text = "\n".join([
        "姓名：林晓宁",
        "本人手机号：13900004025",
        "家庭经济状况：中等收入",
        "德语水平：目前 A2",
        "无关爱好：画画",
        "意向项目：新加坡酒店就业班",
    ])

    _, name, mobile, fields = read_import("资料.txt", text.encode())

    assert (name, mobile) == ("林晓宁", "13900004025")
    assert fields["family_finance"] == "中等收入"
    assert fields["language_ability"] == "德语：目前 A2"
    assert "german" not in fields
    assert "画画" not in fields.values()
    assert "employment" not in fields


def test_screening_uses_the_saved_portrait():
    values = {key: "" for key in ("age", "education", *PORTRAIT_KEYS)}
    values.update(age="28岁", education="高中，已毕业", german="德语 A2", overseas_intent="不想出国")

    notes = portrait_findings("de_vocational", values)

    assert any("28岁" in note and "高中，已毕业" in note for note in notes)
    assert any("移民需求" in note and "学习态度" in note for note in notes)
    assert any("德语 B1" in note for note in notes)
    assert any("留学意愿偏低" in note for note in notes)
    assert portrait_findings("sg_hospitality", values)[0].startswith("画像已记录")


def test_visitor_chat_respects_subject_and_negation():
    assert person_updates("我妹妹18岁，本科已毕业，想去德国") == {}
    assert person_updates("我不是本科毕业，我只有高中学历。") == {"education_level": "senior_secondary"}
    assert person_updates("我还差一年才18岁。") == {}
    notes = portrait_findings("de_vocational", {"german": "我没有考过德语B1，目前只有A1"})
    assert not any("符合匹配企业前" in item for item in notes)


def test_csv_import_preserves_rule_columns_without_copying_identity():
    content = "姓名,手机号,家庭经济状况,语言能力,动手能力,逻辑思维\n测试甲,13900000000,30-50万,德语A2,良好,良好"
    _, _, _, fields = read_import("资料.csv", content.encode())
    assert fields["family_finance"] == "30-50万"
    assert fields["language_ability"] == "德语A2"
    assert "german" not in fields
    assert fields["hands_on"] == fields["logical_thinking"] == "良好"
    assert "13900000000" not in str(fields)


def test_automatic_observation_cannot_replace_verified_fact():
    metadata = {"age": {"source": "advisor_import", "confirmed": True}}
    accepted, evidence = merge_observations({"age": 22}, metadata, {"age": 18}, "customer_chat", "2026-11-17")
    assert accepted == {}
    assert evidence["age"]["confirmed"]
    assert evidence["age"]["conflicts"][0]["value"] == 18


def test_projects_read_single_portrait_with_multiple_languages():
    traits = {"education": "高中毕业", "employment": "找工作", "language_ability": "英语：雅思 6；日语：N2", "german": "B1"}
    document = screening_document("U_002", {"age": 21}, traits, project_label="德国双元制")[0]
    assert document["language_ability"] == "英语：雅思 6；日语：N2；德语：B1"
    assert document["rule_attributes"]["employment"] == "找工作"
    assert not {"singapore", "germany", "german", "age", "education"} & document["rule_attributes"].keys()
    assert any("画像申报达到德语 B1" in note for note in portrait_findings("de_vocational", traits))
    assert any("就业需求：找工作" in note for note in portrait_findings("sg_hospitality", traits))
