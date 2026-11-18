import pytest

from app.core.exceptions import BusinessError
from app.modules.profile.customer_import import read_import, read_import_text
from app.modules.consultant import customer_service
from app.modules.profile.dify_workflow import ReviewPreview
from app.modules.profile.portrait import (
    DE_TRAITS, PORTRAIT_KEYS, SG_TRAITS, merge_observations, person_updates, portrait_findings, screening_document,
    with_portrait_gaps,
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
    assert any("德语 B1" in note for note in notes)
    assert any("留学意愿偏低" in note for note in notes)
    assert portrait_findings("sg_hospitality", values)[0].startswith("画像已记录")


def test_screening_response_lists_all_missing_fields_from_original_snapshot():
    from types import SimpleNamespace

    values = dict.fromkeys(PORTRAIT_KEYS, "已记录")
    values.update(education="大专", admission=None, family_support="  ", immigration=None, learning_attitude=None)
    snapshot = screening_document(
        "U_002", {"gender": "女", "education_stage": "graduated", "intended_major": "机械"},
        values, project_label="新加坡专升本",
    )
    result = {"status": "potential_match", "findings": ["初筛通过。", "画像还没有这些属性：入学能力。"]}
    row = SimpleNamespace(id=1, profile_version=2, background_info={
        "screening": result, "input_snapshot": snapshot,
    })

    response = customer_service._screening_response(row, current_version=3)

    assert response["stale"]
    assert response["result"]["findings"] == (
        "初筛通过。", "画像还没有这些属性：年龄、入学能力、移民需求、家庭支持、学习态度。",
    )
    assert result["findings"] == ["初筛通过。", "画像还没有这些属性：入学能力。"]


def test_filled_snapshot_does_not_report_missing_attributes():
    values = dict.fromkeys(PORTRAIT_KEYS, "已记录")
    values["education"] = "高中"
    snapshot = screening_document("U_002", {
        "age": 0, "gender": "女", "education_stage": "graduated", "intended_major": "机械",
    }, values, project_label="德国双元制")

    assert with_portrait_gaps(("初筛通过。",), snapshot) == ("初筛通过。",)


def test_german_requirement_is_reported_when_other_languages_are_recorded():
    notes = portrait_findings("de_vocational", {"language_ability": "英语：雅思 6"})
    assert any("尚未记录德语水平" in note for note in notes)


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


def test_import_keeps_attributes_from_pages_without_identity():
    text = '姓名：测试客户\f语言能力：雅思6分\f姓名：测试客户\n家庭经济状况：30-50万'
    _, name, mobile, fields = read_import_text(text)
    assert name == '测试客户' and mobile == ''
    assert fields['language_ability'] == '雅思6分'
    assert fields['family_finance'] == '30-50万'
    _, name, mobile, fields = read_import('成绩.csv', '学历,语言能力\n本科,雅思6分'.encode())
    assert name == mobile == ''
    assert fields['education_level'] == 'bachelor'


@pytest.mark.parametrize('text', [
    '姓名：客户甲\f姓名：客户乙\n年龄：22',
    '本人手机号：13900000001\f本人手机号：13900000002\n年龄：22',
    '[{"name":"客户甲","age":22},{"name":"客户乙","age":23}]',
])
def test_partial_identity_still_rejects_multiple_people(text):
    with pytest.raises(BusinessError):
        read_import_text(text)


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


@pytest.mark.parametrize('emphasis', ['', '**'])
def test_advice_keeps_internal_actions_and_customer_words_in_their_own_fields(monkeypatch, emphasis):
    recommendation = '建议顾问先核实英语成绩，收集成绩单，再根据已确认条件安排下一次沟通。'
    talk = '张先生，您目前是否有英语考试成绩？我们可以据此一起核对适合的方向。'
    text = (f'结论：需要补充信息。\n{emphasis}跟进建议{emphasis}：{recommendation}\n'
            f'{emphasis}沟通话术{emphasis}：{talk}\n待补充资料：英语成绩单。')
    monkeypatch.setattr(customer_service, 'review_text', lambda value: ReviewPreview(
        match_result='需要补充信息', match_reason='规则核对结果', advisor_advice=text))
    result = customer_service._generate_advice([{'id': 'U_001', 'name': '张先生'}])
    assert result['recommendation'] == recommendation
    assert result['talk_track'] == talk


@pytest.mark.parametrize('text', ['结论：需要补充信息。跟进建议：请核实英语成绩。',
                                '结论：需要补充信息。沟通话术：您好，请提供英语成绩。'])
def test_incomplete_new_advice_is_not_presented_as_a_complete_result(monkeypatch, text):
    monkeypatch.setattr(customer_service, 'review_text', lambda value: ReviewPreview(
        match_result='需要补充信息', match_reason=text))
    with pytest.raises(BusinessError):
        customer_service._generate_advice([{'id': 'U_001'}])
