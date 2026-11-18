import json
import pytest
from app.ai.workflows.ent_contracts import ACTIONS,plan,format_result,failure_reply


def action(action_name,**params):return json.dumps({'intent':action_name,'params':params},ensure_ascii=False)


@pytest.mark.parametrize('text',[
 'ENT_ACTION: {"intent":"lead_create","customer_name":"验证甲"}',
 'ENT_ACTION:\n{\n"intent":"lead_create",\n"customer_name":"验证甲"\n}',
])
def test_valid_marker_requires_confirmation(text):
 result=plan(text,'录入客户验证甲')
 assert not result['call_api']
 assert json.loads(result['pending'])['state']=='confirm'
 confirmed=plan('', '确认', result['pending'])
 assert confirmed['call_api'] and confirmed['method']=='post'
 assert 'owner_employee_id' not in json.loads(confirmed['http_body'])


@pytest.mark.parametrize('query', ['录入客户','这个功能是否支持录入客户？先不要执行。'])
def test_missing_or_negated_request_never_writes(query):
 for text in ('请提供客户姓名。',action('lead_create',customer_name='未解析姓名')):
  out=plan(text,query)
  assert not out['call_api'] and '未解析姓名' not in out['pending']


def test_unknown_action_and_identity_override_refused():
 assert not plan(action('drop_all'), '执行')['call_api']
 assert not plan(action('lead_create',customer_name='验证甲',owner_employee_id=2),'录入验证甲')['pending']
 assert not plan(action('nl_query',intent='leads_by_status',params={'sql':'select *'}),'查询')['call_api']


def test_cancel_and_confirmation_replay_do_not_write():
 p=plan(action('lead_create',customer_name='验证甲'),'录入验证甲')['pending']
 assert not plan('', '取消', p)['call_api']
 confirmed=plan('', '确认',p)
 assert confirmed['pending']==''
 assert not plan('', '确认',confirmed['pending'])['call_api']


def test_name_resolution_requires_id_and_preserves_pending_action():
 first=plan(action('lead_follow_up',customer_name='验证甲',content='电话沟通'),'为验证甲记跟进电话沟通')
 assert first['call_api'] and first['intent']=='lead_list' and 'keyword=' in first['http_url']
 second=plan('', '选择20',first['pending'])
 assert not second['call_api'] and json.loads(second['pending'])['state']=='confirm'
 third=plan('', '确认',second['pending'])
 assert third['http_url'].endswith('/20/follow-ups')


@pytest.mark.parametrize('code',[0,400,403,404,409,422,500,503])
def test_failures_never_claim_success(code):
 result=format_result(code,'{"code":0,"data":{"id":1}}','lead_create')
 assert '已确认操作成功' not in result['reply']


def test_only_success_status_body_and_record_id_allow_success():
 assert '已确认操作成功' not in format_result(200,'{"code":1}','lead_create')['reply']
 assert '已确认操作成功' not in format_result(200,'{"code":0,"data":null}','lead_create')['reply']
 assert '已确认操作成功' in format_result(200,'{"code":0,"data":{"id":12}}','lead_create')['reply']
 assert '503' in failure_reply('Request failed with status code 503','HTTPError')['reply']
 assert '503' not in failure_reply('connection timeout','TimeoutError')['reply']


@pytest.mark.parametrize('intent',list(ACTIONS))
def test_every_action_uses_only_fixed_backend(intent):
 method,path,required,allowed=ACTIONS[intent]
 assert method in ('get','post','patch','put') and path.startswith('/api/v1/')
 assert set(required.split()) <= set(allowed.split())


def test_reasoning_envelope_does_not_break_strict_final_json():
    text='<think>ignored reasoning, not an action</think>'+action('scores',student_id=101)
    result=plan(text,'查学生101成绩')
    assert result['call_api'] and result['intent']=='scores'
    assert 'student_id=101' in result['http_url']

def test_leave_selection_rejects_unlisted_number_before_confirmation():
    draft = plan(action('leave_approve', student_name='张三', decision='approved'), '同意张三请假')
    assert draft['intent']=='leave_candidates' and draft['method']=='get'
    inferred = plan(action('leave_approve', decision='approved'), '同意张三的请假')
    assert inferred['http_url'] == draft['http_url']
    shortened = plan(action('leave_approve', student_name='同名学生', decision='approved'), '同意联调同名学生的请假')
    from urllib.parse import parse_qs, urlsplit
    assert parse_qs(urlsplit(shortened['http_url']).query)['student_name'] == ['联调同名学生']
    pending = json.loads(draft['pending'])
    pending['choices'] = [23, 26]
    state = json.dumps(pending)
    assert plan('', '选择99', state)['pending'] == state
    selected = plan('', '选择23。', state)
    assert not selected['call_api'] and json.loads(selected['pending'])['state']=='confirm'
    executed = plan('', '确认', selected['pending'])
    assert executed['http_url'].endswith('/leaves/23/approve')
    assert json.loads(executed['http_body']) == {'decision': 'approved'}


def test_formal_report_uses_archive_id_after_confirmation():
    draft = plan(action('formal_report', report_kind='weekly'), '生成正式周报')
    assert not draft['call_api']
    assert plan('', '确认', draft['pending'])['call_api']
    reply = format_result(200, '{"code":0,"data":{"archive_id":321}}', 'formal_report')['reply']
    assert '已归档（编号 321）' in reply


def test_leave_rejection_collects_reason_before_confirming_a_write():
    missing=plan(action('leave_approve',leave_id=23,decision='rejected'),'拒绝请假23')
    assert not missing['call_api'] and 'approval_comment' in missing['reply']
    assert json.loads(missing['pending'])['state']=='collect'
    valid=plan(action('leave_approve',leave_id=23,decision='rejected',approval_comment='请补充材料'),'拒绝请假23，原因请补充材料')
    assert json.loads(valid['pending'])['state']=='confirm'
    assert plan('','确认',valid['pending'])['call_api']


@pytest.mark.parametrize('label,expected',[('低','low'),('普通','medium'),('中','medium'),('中等','medium'),('高','high'),('紧急','urgent')])
def test_chinese_todo_priority_is_validated_before_and_after_confirmation(label,expected):
    draft=plan(action('todo_create',title='演讲准备',priority=label),'新增待办演讲准备，优先级'+label)
    assert not draft['call_api']
    pending=json.loads(draft['pending'])
    assert pending['state']=='confirm' and pending['params']['priority']==expected
    assert not plan('','取消',draft['pending'])['call_api']
    saved=plan('','确认',draft['pending'])
    assert saved['call_api'] and json.loads(saved['http_body'])['priority']==expected
    pending['params']['priority']=label
    assert json.loads(plan('','确认',json.dumps(pending))['http_body'])['priority']==expected
