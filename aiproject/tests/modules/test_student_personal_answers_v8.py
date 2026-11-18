"""V8 regressions: natural account facts, one grounded generation, and safe fallback."""
import asyncio
import json
import pytest
from pydantic import SecretStr
from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.modules.student import assistant_context, assistant_mem0, assistant_dify, assistant_workspace as workspace
from tests.modules.test_student_workspace import db, prepare_turn

PROFILES = [
    {'student_name':'周沐晴','class_teacher':'陆安然','class_name':'新加坡升学一班','abroad_country':'Singapore','major':'计算机科学','student_no':'YJ20260003'},
    {'student_name':'陈思远','class_teacher':'陈思齐','class_name':'德语B1强化班','abroad_country':'Germany','major':'机电一体化','student_no':'YJ20260001'},
]

@pytest.mark.parametrize('profile',PROFILES)
@pytest.mark.parametrize('query,field',[('我叫什么名字','student_name'),('我是谁','student_name'),('我的班主任是谁','class_teacher')])
def test_account_fact_questions_answer_the_requested_fact_without_a_profile_dump(db,monkeypatch,profile,query,field):
    prepare_turn(monkeypatch)
    monkeypatch.setattr(assistant_context,'snapshot',lambda *_:{'profile':profile,'applications':[],'deadlines':[]})
    result=asyncio.run(workspace.run_turn(db,student_id=2,query=query,conversation_id=None,use_dify=False))
    assert profile[field] in result['reply']
    assert not result.get('cards')
    assert '还没有记下' not in result['reply']


def test_teacher_answer_calls_one_readonly_reply_model_with_only_requested_facts(db,monkeypatch):
    prepare_turn(monkeypatch)
    monkeypatch.setattr(assistant_context,'snapshot',lambda *_:{'profile':PROFILES[0],'applications':[{'school':'不相关的学校'}],'deadlines':[]})
    calls=[]
    async def no_plan(**_):pytest.fail('A clear fact question needs no planning call')
    async def model(**kwargs):
        calls.append(kwargs)
        assert kwargs['kind']=='student_fact'
        assert kwargs['reply_evidence']['fields']=={'class_teacher':'陆安然'}
        kwargs['on_text']('你的班主任是陆安然老师。')
        return '你的班主任是陆安然老师。'
    monkeypatch.setattr(assistant_dify,'understand',no_plan)
    monkeypatch.setattr(assistant_dify,'stream_reply',model)
    seen=[]
    result=asyncio.run(workspace.run_turn(db,student_id=2,query='我的班主任是谁',conversation_id=None,use_dify=True,on_text=seen.append))
    assert len(calls)==1 and result['source']=='dify'
    assert result['reply']==seen[-1]=='你的班主任是陆安然老师。'
    assert 'reply_evidence' not in result


def test_missing_official_name_uses_explicit_preferred_name_without_claiming_official_identity(db,monkeypatch):
    prepare_turn(monkeypatch)
    monkeypatch.setattr(assistant_context,'snapshot',lambda *_:{'profile':{},'applications':[],'deadlines':[]})
    monkeypatch.setattr(assistant_mem0,'search_memories',lambda *_,**__:['学生姓名：小晴'])
    result=asyncio.run(workspace.run_turn(db,student_id=2,query='我叫什么名字',conversation_id=None,use_dify=False))
    assert '小晴' in result['reply'] and '称呼' in result['reply']
    assert '学籍' in result['reply']


def test_official_name_and_preferred_name_remain_distinct(db,monkeypatch):
    prepare_turn(monkeypatch)
    monkeypatch.setattr(assistant_context,'snapshot',lambda *_:{'profile':PROFILES[0],'applications':[],'deadlines':[]})
    monkeypatch.setattr(assistant_mem0,'search_memories',lambda *_,**__:['学生姓名：小晴'])
    result=asyncio.run(workspace.run_turn(db,student_id=2,query='你记得我叫什么吗',conversation_id=None,use_dify=False))
    assert '周沐晴' in result['reply'] and '小晴' in result['reply']


def test_model_unavailable_keeps_the_verified_fact_answer_instead_of_generic_failure(db,monkeypatch):
    prepare_turn(monkeypatch)
    monkeypatch.setattr(assistant_context,'snapshot',lambda *_:{'profile':PROFILES[0],'applications':[],'deadlines':[]})
    async def offline(**kwargs):raise BusinessError(502,'offline')
    monkeypatch.setattr(assistant_dify,'stream_reply',offline)
    result=asyncio.run(workspace.run_turn(db,student_id=2,query='我的班主任是谁',conversation_id=None,use_dify=True))
    assert '陆安然' in result['reply'] and '未能完成' not in result['reply']
    assert result['source']=='student_record'


def test_gateway_passes_trusted_evidence_but_not_unrelated_official_records(monkeypatch):
    monkeypatch.setattr(get_settings(),'stu_dify_api_key',SecretStr('test-only'))
    evidence={'kind':'student_record','question':'我的班主任是谁','fields':{'class_teacher':'陆安然'},'missing_fields':[]}
    async def upstream(url,key,timeout,payload,on_text,**budgets):
        context=json.loads(payload['inputs']['reply_context_json'])
        assert context['reply_evidence']==evidence
        assert '其他学生' not in json.dumps(payload,ensure_ascii=False)
        assert 'student_access_token' not in payload['inputs']
        on_text('你的班主任是陆安然老师。')
        return {'answer':'你的班主任是陆安然老师。'}
    monkeypatch.setattr(assistant_dify,'chat_messages',upstream)
    reply=asyncio.run(assistant_dify.stream_reply(query='我的班主任是谁',context={'profile':PROFILES[0],'applications':[{'school':'其他学生'}]},history=[],memories=[],user_key='stu_2',country='Singapore',reviewed_reply='你的班主任是陆安然老师。',kind='student_fact',reply_evidence=evidence,on_text=lambda _:None))
    assert '陆安然' in reply


@pytest.mark.parametrize('query,intent',[('我要投诉我的班主任，他总是迟到','feedback'),('我要请假，找班主任审批','leave_create'),('我叫小晴','chat'),('计算机专业有什么课程','chat'),('新加坡有哪些学校','chat')])
def test_profile_question_routing_does_not_steal_actions_or_general_topics(query,intent):
    assert workspace.local_understanding(query,None).intent==intent


def test_official_name_wording_selects_name_not_the_whole_profile(db,monkeypatch):
    prepare_turn(monkeypatch)
    monkeypatch.setattr(assistant_context,'snapshot',lambda *_:{'profile':PROFILES[0],'applications':[],'deadlines':[]})
    r=asyncio.run(workspace.run_turn(db,student_id=2,query='我的学籍姓名是什么',conversation_id=None,use_dify=False))
    assert '周沐晴' in r['reply'] and not r.get('cards')
