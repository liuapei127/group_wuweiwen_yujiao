import json
from types import SimpleNamespace
from unittest.mock import Mock

from app.ai.assistant.replies import business_reply, chat_history, conversational_reply, display_stored_reply
from app.ai.assistant.service import AssistantService


def test_organizations_are_grouped_by_parent_in_live_and_historical_replies():
    rows = [
        {"id": 3, "parent_id": 1, "org_name": "咨询部", "manager_id": 77},
        {"id": 1, "parent_id": None, "org_name": "教育服务", "create_time": "internal-time"},
        {"id": 4, "parent_id": 99, "org_name": "独立检索结果"},
    ]
    expected = "查到 3 个组织：\n• 教育服务\n  └ 咨询部\n• 独立检索结果"
    reply = business_reply(200, json.dumps({"code": 0, "data": rows}), "organizations")
    assert reply == expected
    message = {
        "role": "assistant",
        "content": "后端查询结果（仅来自实际响应）：\n" + json.dumps(rows),
        "metadata": {"action": "organizations"},
    }
    assert display_stored_reply(message) == expected
    assert display_stored_reply({**message, "role": "user"}) == message["content"]


def test_customer_list_uses_labeled_status_and_omits_contact_information():
    payload = {"code": 0, "data": {"total": 2, "items": [
        {"id": 81, "customer_name": "测试客户", "status": "contacting",
         "intended_country": "德国", "contact_info": "private-contact"},
    ]}}
    body = json.dumps(payload)
    reply = business_reply(200, body, "lead_list")
    assert "测试客户（编号 81） · 联系中 · 意向 德国" in reply
    assert "查到 2 位客户" in reply and "当前显示 1 位" in reply
    assert "private-contact" not in reply
    assert "无权操作" in business_reply(403, body, "lead_list")


def test_score_reply_handles_no_records_and_formats_existing_scores():
    empty = '{"code":0,"data":[]}'
    assert business_reply(200, empty, "scores") == "没有查到这名学生的成绩记录。"
    data = [{"course_name": "德语", "score": 0, "semester": "第一学期", "id": 6, "version": 2}]
    reply = business_reply(200, json.dumps({"code": 0, "data": data}), "scores")
    assert "德语 · 0 分 · 第一学期 · 成绩编号 6 · 版本 2" in reply
    old = {"role": "assistant", "metadata": {"action": "scores"},
           "content": "后端查询结果（仅来自实际响应）：\n[]"}
    assert display_stored_reply(old) == business_reply(200, empty, "scores")


def test_greeting_keeps_pending_confirmation_and_does_not_call_external_services():
    queued = '{"state":"confirm","intent":"todo_create","params":{"title":"跟进"}}'
    extractor = Mock()
    executor = Mock()
    assistant = AssistantService(Mock(), extractor=extractor, executor=executor)
    assistant.repo = Mock()
    assistant.repo.get.return_value = {"pending": queued}
    assistant.repo.reserve.return_value = "nonce"
    assistant.detail = Mock()
    assistant.send("demo", SimpleNamespace(text="你好！", expected_version=1),
                   SimpleNamespace(employee_id=10, permissions=frozenset()), "unused-token")

    _, _, _, _, pending, _, reply, metadata = assistant.repo.finish.call_args.args
    assert pending == queued and reply.startswith("你好，我是 ENT 助手")
    assert metadata["source"] == "服务端" and not metadata["executed"]
    extractor.extract.assert_not_called()
    executor.assert_not_called()
    assert conversational_reply("Test?").startswith("消息已收到")
    assert conversational_reply("你好，请查询组织架构") is None


def test_capabilities_list_only_granted_features():
    reply = conversational_reply("你有什么功能吗？", {"todos:read", "todos:write"})
    assert "可以和你聊聊" in reply and "待办" in reply
    assert "确认" in reply and "学生成绩" not in reply


def test_chat_receives_only_recent_small_talk_and_preserves_pending_action():
    queued = '{"state":"confirm","intent":"todo_create","params":{"title":"跟进"}}'
    messages = [
        {"role": "user", "content": "查询客户", "metadata": {}},
        {"role": "assistant", "content": "内部客户资料", "metadata": {"action": "lead_list"}},
        {"role": "user", "content": "讲个动物笑话", "metadata": {}},
        {"role": "assistant", "content": "猫的笑话", "metadata": {"mode": "chat"}},
    ]
    extractor = Mock()
    extractor.extract.return_value = '{"intent":"chat","params":{},"reply":"这次讲企鹅吧。"}'
    executor = Mock()
    assistant = AssistantService(Mock(), extractor=extractor, executor=executor)
    assistant.repo = Mock()
    assistant.repo.get.return_value = {"pending": queued}
    assistant.repo.reserve.return_value = "nonce"
    assistant.repo.history.return_value = messages
    assistant.detail = Mock()
    assistant.send("demo", SimpleNamespace(text="换一种动物", expected_version=1),
                   SimpleNamespace(employee_id=10, permissions={"todos:write"}), "unused-token")

    extractor.extract.assert_called_once_with("换一种动物", queued, chat_history(messages))
    assert json.loads(chat_history(messages)) == [{"user": "讲个动物笑话", "assistant": "猫的笑话"}]
    _, _, _, _, pending, _, reply, metadata = assistant.repo.finish.call_args.args
    assert pending == queued and reply == "这次讲企鹅吧。"
    assert metadata["mode"] == "chat" and not metadata["executed"]
    executor.assert_not_called()


def test_todo_details_and_legacy_history_show_returned_values_without_internal_fields():
    row = {'id':378,'title':'待处理投诉','todo_type':'complaint_follow','status':'pending',
           'priority':'medium','due_time':'2026-11-18T10:16:22','description':None,
           'related_type':'student_feedback_ticket','related_id':271,'completed_time':None,
           'assignee_id':1000010,'assignment_version':1,'source_status':'pending'}
    rendered = business_reply(200,json.dumps({'code':0,'data':[row]}),'todos')
    for expected in ('待办编号：378','标题：待处理投诉','待办类型：投诉跟进','状态：待处理',
                     '优先级：中','到期时间：2026-11-18 10:16:22','说明：未提供','关联编号：271'):
        assert expected in rendered
    assert 'assignee_id' not in rendered and '1000010' not in rendered and 'assignment_version' not in rendered
    assert '后端查询结果' not in rendered and '[{' not in rendered
    old = {'role':'assistant','metadata':{'action':'todos'},
           'content':'后端查询结果（仅来自实际响应）：\n'+json.dumps([row])}
    assert display_stored_reply(old) == rendered
    assert '无权操作' in business_reply(403,json.dumps({'code':0,'data':[row]}),'todos')
    assert '待处理投诉' not in business_reply(403,json.dumps({'code':0,'data':[row]}),'todos')


def test_detail_rendering_handles_no_records_and_nested_query_results():
    assert '没有找到' in business_reply(200,'{"code":0,"data":[]}','todos')
    assert '格式有误' in business_reply(200,'{"code":0,"data":"invalid"}','todos')
    data = {'intent':'lead_detail_by_name','result':{
        'lead':{'id':5,'customer_name':'客户甲','status':'contacting'},
        'follow_ups':[{'id':7,'content':'已电话确认材料','follow_type':'phone'}]}}
    result = business_reply(200,json.dumps({'code':0,'data':data}),'nl_query')
    assert '客户姓名：客户甲' in result and '已电话确认材料' in result and '跟进方式：电话' in result
    assert '没有找到' in business_reply(200,json.dumps({'code':0,'data':{
        'intent':'lead_detail_by_name','result':{'rows':[]}}}),'nl_query')


def test_history_corrections_and_long_result_disclose_limits():
    row = {'id':1,'score_id':8,'version':2,'operation':'correct','change_reason':'核对卷面',
           'before_data':{'score':80,'submission_hash':'internal'},'after_data':{'score':85}}
    result = business_reply(200,json.dumps({'code':0,'data':[row]}),'score_history')
    assert '更正前：成绩：80' in result and '更正后：成绩：85' in result
    assert 'internal' not in result
    rows = [{'id':i,'title':'待办'+str(i)} for i in range(31)]
    assert '前 30 条' in business_reply(200,json.dumps({'code':0,'data':rows}),'todos')
    assert '已截取前段' in business_reply(200,json.dumps({'code':0,'data':[{'id':1,'title':'测试','description':'字'*13000}]}),'todos')


def test_confirmation_history_uses_business_labels_without_raw_action_json():
    message={'role':'assistant','content':'请核对以下操作，回复“确认”才会提交；回复“取消”放弃。\ntodo_create\n{"title":"演讲准备"}',
             'metadata':{'action':'todo_create','executed':False}}
    reply=display_stored_reply(message)
    assert '新增待办' in reply and '确认后才会提交' in reply and '取消' in reply
    assert 'todo_create' not in reply and '{' not in reply
    assert display_stored_reply({**message,'role':'user'})==message['content']
