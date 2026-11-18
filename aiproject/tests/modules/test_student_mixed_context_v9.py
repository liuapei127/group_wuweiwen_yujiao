"""A turn shares owned evidence across mixed questions and stream recovery."""
import asyncio
import pytest
from app.core.exceptions import BusinessError
from app.modules.student import assistant_context, assistant_mem0, assistant_dify, assistant_personal
from app.modules.student import assistant_workspace as workspace
from app.modules.student.assistant_reply_stream import ReplyGate, StudentReplyInterrupted
from tests.modules.test_student_workspace import db, prepare_turn

PROFILE={'student_name':'周沐晴','class_teacher':'陆安然','major':'计算机科学','abroad_country':'Singapore','class_name':'2026秋季新加坡升学一班'}
MEMORIES=['学生自述：我喜欢吃苹果','学生自述：我喜欢健康饮食']

@pytest.mark.parametrize('query',['我喜欢吃什么 我是谁','我是谁，还有我喜欢吃什么？','我的班主任是谁，我叫什么名字'])
def test_mixed_owned_questions_are_not_plain_chat(query):
 assert workspace.local_understanding(query,None).intent=='profile'

def test_mixed_fact_answer_selects_only_requested_facts_and_explicit_memories():
 r=assistant_personal.answer('我喜欢吃什么 我是谁',PROFILE,memories=MEMORIES)
 assert '周沐晴' in r['reply'] and '苹果' in r['reply']
 assert r['reply_evidence']['self_reports']==MEMORIES
 assert 'class_name' not in r['reply_evidence']['fields']
 assert '2026' not in r['reply']

@pytest.mark.parametrize('query',['我要投诉我的班主任，我是谁','我要请假，我叫什么名字','我喜欢吃苹果','我是谁写的这本书'])
def test_mixed_detection_does_not_take_business_or_statements(query):
 assert workspace.local_understanding(query,None).intent!='profile'

def test_model_receives_and_checks_same_official_and_memory_evidence(db,monkeypatch):
 prepare_turn(monkeypatch)
 monkeypatch.setattr(assistant_context,'snapshot',lambda *_:{'profile':PROFILE,'applications':[],'deadlines':[]})
 monkeypatch.setattr(assistant_mem0,'search_memories',lambda *_,**__:MEMORIES)
 async def model(**kw):
  assert kw['kind']=='student_fact'
  assert kw['reply_evidence']['fields']['student_name']=='周沐晴'
  assert kw['reply_evidence']['self_reports']==MEMORIES
  g=ReplyGate(kind=kw['kind'],reply_evidence=kw['reply_evidence'],reviewed_reply=kw['reviewed_reply'],query=kw['query'],history=kw['history'],on_text=kw['on_text'])
  return g.finish('你之前说你喜欢吃苹果。你的学籍姓名是周沐晴，专业是计算机科学。')
 monkeypatch.setattr(assistant_dify,'stream_reply',model)
 r=asyncio.run(workspace.run_turn(db,student_id=2,query='我喜欢吃什么 我是谁',conversation_id=None,use_dify=True))
 assert r['source']=='dify' and '苹果' in r['reply'] and '周沐晴' in r['reply']
 assert not r.get('reply_notice')

@pytest.mark.parametrize('bad',['你喜欢吃香蕉。你的学籍姓名是周沐晴。','你喜欢吃苹果和香蕉。你的学籍姓名是周沐晴。','你的学籍姓名是陈思远。'])
def test_mixed_evidence_does_not_authorize_other_preferences_or_accounts(bad):
 evidence=assistant_personal.answer('我喜欢吃什么 我是谁',PROFILE,memories=MEMORIES)['reply_evidence']
 with pytest.raises(BusinessError):
  ReplyGate(kind='student_fact',reply_evidence=evidence,reviewed_reply='',query='我喜欢吃什么 我是谁',history=[],on_text=lambda _:None).finish(bad)

def test_verified_prefix_is_completed_after_rejection_without_fake_network_notice(db,monkeypatch):
 prepare_turn(monkeypatch)
 monkeypatch.setattr(assistant_context,'snapshot',lambda *_:{'profile':PROFILE,'applications':[],'deadlines':[]})
 monkeypatch.setattr(assistant_mem0,'search_memories',lambda *_,**__:MEMORIES)
 seen=[]
 async def model(**kw):
  prefix='你喜欢吃苹果。'
  kw['on_text'](prefix)
  raise StudentReplyInterrupted(safe_partial=prefix,reason_code='reply_rejected')
 monkeypatch.setattr(assistant_dify,'stream_reply',model)
 r=asyncio.run(workspace.run_turn(db,student_id=2,query='我喜欢吃什么 我是谁',conversation_id=None,use_dify=True,on_text=seen.append))
 assert r['reply'].startswith(seen[0]) and '周沐晴' in r['reply']
 assert not r.get('reply_notice')
 assert all(b.startswith(a) for a,b in zip(seen,seen[1:]))

def test_real_timeout_still_keeps_interruption_notice(db,monkeypatch):
 prepare_turn(monkeypatch)
 monkeypatch.setattr(assistant_context,'snapshot',lambda *_:{'profile':PROFILE,'applications':[],'deadlines':[]})
 async def model(**kw):
  kw['on_text']('你的班主任是陆安然。')
  raise StudentReplyInterrupted(safe_partial='你的班主任是陆安然。',reason_code='reply_timeout')
 monkeypatch.setattr(assistant_dify,'stream_reply',model)
 r=asyncio.run(workspace.run_turn(db,student_id=2,query='我的班主任是谁',conversation_id=None,use_dify=True))
 assert '中断' in r['reply_notice']

def test_railway_alias_is_allowed_only_when_its_canonical_entity_is_in_evidence():
 evidence={'kind':'knowledge','country':'Germany','records':[{'answer':'到德国铁路官方渠道查路线、换乘与时刻。','steps':[]}]}
 def g():return ReplyGate(kind='grounded_knowledge',reply_evidence=evidence,reviewed_reply='',query='德国交通怎么样',history=[],on_text=lambda _:None)
 assert g().finish('可以通过德国铁路（DB）官方渠道查路线。')
 for text in ['通过DB Navigator买票。','使用VBB查询。','到便利店购买车票。']:
  with pytest.raises(BusinessError):g().finish(text)
 evidence['records'][0]['answer']='到当地公交运营方查询路线。'
 with pytest.raises(BusinessError):g().finish('可以通过DB查路线。')


def test_recovery_uses_real_line_breaks_and_preserves_exact_visible_prefix():
 from app.modules.student.assistant_reply_stream import complete_reviewed_reply
 prefix='已核实的第一句。\n'
 result=complete_reviewed_reply(prefix,'已核实的第一句。第二句。')
 assert result.startswith(prefix) and result.count('已核实的第一句')==1
 assert '\\n' not in result and '第二句' in result

def test_memory_claims_can_be_separate_streamed_lines_without_becoming_official_facts():
 evidence=assistant_personal.answer('我喜欢吃什么 我是谁',PROFILE,memories=MEMORIES)['reply_evidence']
 g=ReplyGate(kind='student_fact',reply_evidence=evidence,reviewed_reply='',query='我喜欢吃什么 我是谁',history=[],on_text=lambda _:None)
 assert g.finish('你之前说你喜欢吃苹果。\n你的学籍姓名是周沐晴。')
 with pytest.raises(BusinessError):
  ReplyGate(kind='student_fact',reply_evidence=evidence,reviewed_reply='',query='我喜欢吃什么 我是谁',history=[],on_text=lambda _:None).finish('你的学籍姓名是周沐晴。')


def test_memory_only_reply_cannot_add_unselected_personal_biography():
 evidence=assistant_personal.answer('我喜欢吃什么',PROFILE,memories=MEMORIES)['reply_evidence']
 assert evidence['fields']=={}
 def gate():return ReplyGate(kind='student_fact',reply_evidence=evidence,reviewed_reply='',query='我喜欢吃什么',history=[],on_text=lambda _:None)
 assert gate().finish('你喜欢吃苹果。')
 with pytest.raises(BusinessError):gate().finish('你喜欢吃苹果。你出生在北京。')


def test_grounded_recovery_does_not_repeat_already_answered_personal_fields():
 from app.modules.student.assistant_reply_stream import complete_reviewed_reply
 r=assistant_personal.answer('我喜欢吃什么 我是谁',PROFILE,memories=MEMORIES)
 prefix='你是周沐晴，专业是计算机科学。\n'
 text=complete_reviewed_reply(prefix,r['reply'],r['reply_evidence'])
 assert text.startswith(prefix) and text.count('周沐晴')==1 and text.count('计算机科学')==1
 assert '苹果' in text

def test_missing_preference_must_be_addressed_even_when_name_is_answered():
 evidence=assistant_personal.answer('我喜欢吃什么 我是谁',PROFILE,memories=[])['reply_evidence']
 with pytest.raises(BusinessError):
  ReplyGate(kind='student_fact',reply_evidence=evidence,reviewed_reply='',query='我喜欢吃什么 我是谁',history=[],on_text=lambda _:None).finish('你的学籍姓名是周沐晴。')

def test_public_answer_does_not_invent_punctuality_assurance():
 evidence={'kind':'knowledge','country':'Germany','records':[{'answer':'通过德国铁路官方渠道查询路线。'}]}
 seen=[]
 with pytest.raises(BusinessError):
  ReplyGate(kind='grounded_knowledge',reply_evidence=evidence,reviewed_reply='',query='交通怎么样',history=[],on_text=seen.append).accept('德国交通整体高效、准点率高。')
 assert seen==[]


def test_knowledge_recovery_keeps_numbered_steps_on_separate_lines():
 from app.modules.student.assistant_reply_stream import complete_reviewed_reply
 reply=complete_reviewed_reply('先确认路线。\n','先确认路线。\n\n1. 核对票种。\n2. 再核对有效范围。')
 assert reply.count('先确认路线')==1 and '\n2. 再核对有效范围。' in reply
