"""Natural replies may use owned evidence, without granting new facts or actions."""
import pytest

from app.core.exceptions import BusinessError
from app.modules.student.assistant_reply_stream import ReplyGate


def personal(**fields):
    return {"kind": "student_record", "question": "我的班主任是谁", "fields": fields}


def knowledge():
    return {"kind": "knowledge", "country": "Singapore", "depth": "detailed", "records": [{
        "key": "Singapore/transport/0", "question": "公交怎么买票",
        "answer": "使用符合条件的非接触银行卡。乘车前确认卡片适用。",
        "steps": ["先查看路线。", "上车与下车使用同一张卡片感应。"],
        "source_url": "https://example.test/official", "verified_at": "2026-11-18",
    }]}


def gate(kind, evidence, seen=None, **kw):
    return ReplyGate(kind=kind, reply_evidence=evidence, reviewed_reply="", query="请回答",
                     history=[], on_text=(seen if seen is not None else []).append, **kw)


def test_known_teacher_and_official_name_are_natural_not_an_entire_profile():
    assert gate("student_fact", personal(class_teacher="陆安然")).finish("你的班主任是陆安然老师。")
    assert gate("student_fact", personal(student_name="周沐晴")).finish("你的学籍姓名是周沐晴。")


def test_verified_student_number_and_class_year_are_allowed():
    evidence = personal(student_no="YJ20260003", class_name="2026秋季新加坡升学一班")
    assert gate("student_fact", evidence).finish("你的学号是YJ20260003，班级是2026秋季新加坡升学一班。")


@pytest.mark.parametrize("reply", ["你的班主任是王老师。", "王老师是你的班主任。", "你叫陈思远。"])
def test_wrong_personal_field_is_rejected_before_emitting(reply):
    seen = []
    g = gate("student_fact", personal(class_teacher="陆安然", student_name="周沐晴"), seen)
    with pytest.raises(BusinessError):
        g.accept(reply)
    assert seen == []


def test_missing_teacher_does_not_borrow_another_name_or_student_claim():
    evidence = personal(student_name="周沐晴", class_teacher=None)
    assert gate("student_fact", evidence).finish("目前没有登记你的班主任信息。")
    with pytest.raises(BusinessError):
        gate("student_fact", evidence).finish("你的班主任是周沐晴。")


def test_destination_does_not_establish_actual_location_or_enrollment():
    for reply in ["你现在在新加坡学习。", "你已经入学了。"]:
        with pytest.raises(BusinessError):
            gate("student_fact", personal(abroad_country="Singapore")).finish(reply)


def test_only_official_selected_fields_authorize_numeric_facts():
    g = ReplyGate(kind="student_fact", reply_evidence=personal(student_no="YJ20260003"),
                  reviewed_reply="", query="我的班主任电话13812345678？", history=[], on_text=lambda _: None)
    with pytest.raises(BusinessError):
        g.finish("你的班主任电话是13812345678。")


def test_knowledge_can_rephrase_and_expand_curated_steps():
    answer = "1. 先查看出行路线。\n2. 乘坐公交时，上下车用同一张适用卡片感应。"
    assert gate("grounded_knowledge", knowledge()).finish(answer) == answer


@pytest.mark.parametrize("reply", [
    "票价是2元。", "需要10分钟。", "需要十分钟。", "请拨打123456。",
    "请查看https://example.test/official。", "你已经入学了。",
    "我已经帮你提交申请。", "我现在帮你联系老师。", "建议服用药物。",
])
def test_grounding_does_not_allow_unsupported_numbers_tools_or_medical_claims(reply):
    seen = []
    with pytest.raises(BusinessError):
        gate("grounded_knowledge", knowledge(), seen).accept(reply)
    assert not seen


def test_source_dates_and_question_numbers_are_not_claim_evidence():
    evidence = knowledge()
    evidence["records"][0]["question"] = "票价是不是18元"
    with pytest.raises(BusinessError):
        gate("grounded_knowledge", evidence).finish("票价是18元。")


def test_grounded_stream_preserves_checked_prefix_when_later_fact_is_wrong():
    seen = []
    g = gate("student_fact", personal(class_teacher="陆安然"), seen)
    g.accept("你的班主任是陆安然老师。")
    with pytest.raises(BusinessError):
        g.accept("你的班主任是陆安然老师。电话号码是123456。")
    assert seen == ["你的班主任是陆安然老师。"]
    assert g.visible == seen[0]


def test_grounded_mode_requires_matching_backend_evidence():
    for evidence in [None, {}, {"kind": "knowledge", "records": []}]:
        with pytest.raises(BusinessError):
            gate("student_fact", evidence).finish("你好。")


def test_known_number_cannot_be_reused_as_a_different_measure():
    evidence = knowledge()
    evidence["records"][0]["answer"] = "步行约10分钟。"
    with pytest.raises(BusinessError):
        gate("grounded_knowledge", evidence).finish("票价是10元。")


def test_missing_preferred_name_does_not_authorize_invented_remembered_nickname():
    with pytest.raises(BusinessError):
        gate("student_fact", personal(student_name="周沐晴")).finish("你之前希望我叫你小王。")


def test_confirmed_preferred_name_and_official_name_remain_distinct():
    evidence = personal(student_name="周沐晴", preferred_name="小晴")
    assert gate("student_fact", evidence).finish("你的学籍姓名是周沐晴，你之前希望我叫你小晴。")
    with pytest.raises(BusinessError):
        gate("student_fact", evidence).finish("你的学籍姓名是小晴。")


def test_unknown_chinese_age_cannot_be_added_to_a_profile():
    with pytest.raises(BusinessError):
        gate("student_fact", personal(student_name="周沐晴")).finish("你是周沐晴，今年二十一岁。")


def test_required_personal_field_must_appear_in_final_answer():
    evidence = {**personal(class_teacher="陆安然"), "required_fields": ["class_teacher"]}
    with pytest.raises(BusinessError):
        gate("student_fact", evidence).finish("我在这里陪着你。")


def test_markdown_emphasis_around_a_verified_name_is_not_a_new_fact():
    assert gate("student_fact", personal(class_teacher="陆安然")).finish("你的班主任是**陆安然**老师。")


def test_spacing_cannot_hide_a_wrong_named_field():
    with pytest.raises(BusinessError):
        gate("student_fact", personal(class_teacher="陆安然")).finish("你的班主任 是 王老师。")


def test_explicit_contradiction_of_an_official_identity_is_rejected():
    evidence = {**personal(student_name="周沐晴"), "required_fields": ["student_name"]}
    with pytest.raises(BusinessError):
        gate("student_fact", evidence).finish("你不是周沐晴。")


@pytest.mark.parametrize("reply", ["王老师负责带你。", "由王老师担任班主任。", "王明负责指导你的学习。"])
def test_named_teacher_paraphrase_is_rejected_before_stream_emission(reply):
    seen = []
    evidence = {**personal(class_teacher="陆安然"), "required_fields": ["class_teacher"]}
    with pytest.raises(BusinessError):
        gate("student_fact", evidence, seen).accept(reply)
    assert seen == []


def test_supported_teacher_paraphrase_and_harmless_intro_remain_usable():
    seen = []
    evidence = {**personal(class_teacher="陆安然"), "required_fields": ["class_teacher"]}
    g = gate("student_fact", evidence, seen)
    g.accept("我看了一下你的资料。")
    g.accept("我看了一下你的资料。陆安然老师负责带你。")
    assert g.finish("我看了一下你的资料。陆安然老师负责带你。")


def test_good_fact_cannot_launder_a_different_named_teacher_in_same_sentence():
    seen = []
    evidence = {**personal(student_name="周沐晴", class_teacher="陆安然"), "required_fields": ["class_teacher"]}
    with pytest.raises(BusinessError):
        gate("student_fact", evidence, seen).accept("周沐晴，王老师负责带你，学籍登记陆安然。")
    assert seen == []


def test_recorded_country_alias_is_supported_without_claiming_current_location():
    assert gate("student_fact", personal(abroad_country="Singapore")).finish("你的留学方向是新加坡。")


def test_known_teacher_does_not_authorize_an_extra_coordinator():
    seen = []
    with pytest.raises(BusinessError):
        gate("student_fact", personal(class_teacher="陆安然"), seen).accept("陆安然老师和张三共同负责带你。")
    assert seen == []


@pytest.mark.parametrize("reply", [
    "可以使用DB Navigator、VBB或RMV App购票。",
    "可在Kiosk或REWE购买。",
    "可以使用EZ-Link卡或NETS FlashPay卡。",
    "在便利店或邮局充值就可以。",
    "在地铁站的售票机购买单程票。",
    "游客通行证对游客更省事。",
    "也可以购买月票，通常更划算。",
])
def test_new_products_channels_and_ticket_types_are_rejected_before_emission(reply):
    seen = []
    with pytest.raises(BusinessError):
        gate("grounded_knowledge", knowledge(), seen).accept(reply)
    assert seen == []


def test_supported_payment_brands_and_curated_purchase_channels_can_be_paraphrased():
    evidence = knowledge()
    evidence["records"][0]["answer"] = "SimplyGo支持符合条件的Visa和Mastercard非接触银行卡。"
    evidence["records"][0]["steps"] = ["可在官方应用或售票机购票；先确认票种和区域。"]
    assert gate("grounded_knowledge", evidence).finish("你可以使用符合条件的Visa或Mastercard银行卡，通过SimplyGo乘车。")
    assert gate("grounded_knowledge", evidence).finish("购票前先确认票种和区域，再使用官方应用或售票机购票。")


def test_brand_in_source_url_or_question_does_not_authorize_a_product_claim():
    evidence = knowledge()
    evidence["records"][0]["question"] = "EZ-Link卡在哪买？"
    evidence["records"][0]["source_url"] = "https://www.ez-link.test/"
    with pytest.raises(BusinessError):
        gate("grounded_knowledge", evidence).accept("可以使用EZ-Link卡。")


def test_unknown_product_can_be_acknowledged_as_missing_information():
    assert gate("grounded_knowledge", knowledge()).finish("当前资料没有说明EZ-Link卡的购买方式，无法确认是否可在邮局充值。")


def test_a_sales_outlet_cannot_be_streamed_before_its_purchase_verb_arrives():
    evidence = knowledge()
    evidence["records"][0]["steps"] = ["可通过官方应用购票。"]
    seen = []
    with pytest.raises(BusinessError):
        gate("grounded_knowledge", evidence, seen).accept("你可以先去便利店，那里能买票。")
    assert seen == []


def test_official_name_question_does_not_stream_a_nickname_as_the_name():
    evidence = {**personal(student_name="周沐晴", preferred_name="小晴"), "required_fields": ["student_name"]}
    seen = []
    with pytest.raises(BusinessError):
        gate("student_fact", evidence, seen).accept("你叫小晴。")
    assert seen == []
    assert gate("student_fact", evidence).finish("你的学籍姓名是周沐晴，你希望我称呼你为小晴。")


@pytest.mark.parametrize("reply", [
    "如果不确定就去便利店购买EZ-Link卡。",
    "不清楚的话可以到邮局充值。",
    "当前资料没有说明购买方式但可以去便利店购买。",
])
def test_uncertainty_cannot_launder_positive_unsupported_recommendations(reply):
    seen = []
    with pytest.raises(BusinessError):
        gate("grounded_knowledge", knowledge(), seen).accept(reply)
    assert seen == []


def test_knowledge_heading_is_withheld_so_rejected_steps_can_use_verified_fallback():
    seen = []
    g = gate("grounded_knowledge", knowledge(), seen)
    g.accept("在新加坡坐公交，可以按以下方式购票： \n")
    assert seen == []
    with pytest.raises(BusinessError):
        g.accept("在新加坡坐公交，可以按以下方式购票： \n到便利店购买EZ-Link卡。")
    assert g.visible == ""


def test_knowledge_heading_alone_cannot_finish_as_a_useful_answer():
    with pytest.raises(BusinessError):
        gate("grounded_knowledge", knowledge()).finish("可以按以下步骤操作：")


def test_knowledge_heading_and_verified_step_still_stream_together():
    seen = []
    g = gate("grounded_knowledge", knowledge(), seen)
    reply = "乘车步骤如下：\n上下车保持使用同一张卡片。"
    g.accept(reply)
    assert seen == [reply]
    assert g.finish(reply) == reply
