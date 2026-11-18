"""Legacy showcase FAQs must expand real steps and preserve student intent."""
import pytest
from app.modules.student import assistant_knowledge as knowledge


@pytest.fixture
def legacy_catalog(monkeypatch):
    def install(country, *, steps=None, answer=None):
        row = {
            'country': country, 'category': 'transport', 'title': '公共交通指南',
            'content': '已审核的公交票务资料', 'source_title': '运营方',
            'source_url': 'https://example.invalid/transport', 'verified_at': '2026-11-18',
            'details': {'scope': '按所在城市及票种核对', 'steps': steps if steps is not None else [
                '先核对银行卡或车票的适用范围及余额。',
                '上下车使用同一张卡片，核对行程记录。',
                '租房前与房东核对押金。',
            ], 'faqs': [{
                'question': '当地公交可以刷银行卡吗？',
                'answer': answer or '可以使用适用的银行卡或车票，使用前核对适用范围。',
                'keywords': ['公交', '银行卡', '买票', '购票'], 'topic': 'payment',
            }]},
        }
        monkeypatch.setattr(knowledge.repository, 'iter_life_knowledge', lambda *_: [row])
        return row
    return install


@pytest.mark.parametrize('country', ['Germany', 'Singapore'])
def test_legacy_detail_expands_reviewed_steps_without_rewriting_question(legacy_catalog, country):
    legacy_catalog(country)
    query = '我想坐公交，怎么买票？'
    brief = knowledge.answer(None, country, query)
    choice = brief['choices'][0]
    assert query in choice['query']
    assert '当地公交可以刷银行卡吗' not in choice['query']
    detailed = knowledge.answer(None, country, choice['query'], history=[{'role': 'user', 'content': query}])
    assert detailed['reply'] != brief['reply']
    assert '适用范围及余额' in detailed['reply'] and '同一张卡片' in detailed['reply']
    assert '房东' not in detailed['reply'] and '押金' not in detailed['reply']
    assert detailed['knowledge_keys'] == brief['knowledge_keys']
    assert detailed['choices'] == []


@pytest.mark.parametrize('country', ['Germany', 'Singapore'])
def test_brief_result_carries_structured_source_evidence_and_steps(legacy_catalog, country):
    row = legacy_catalog(country)
    result = knowledge.answer(None, country, '公交怎么买票？')
    evidence = result['reply_evidence']
    assert evidence['kind'] == 'knowledge' and evidence['country'] == country
    assert evidence['depth'] == 'brief' and '公交怎么买票' in evidence['question']
    record = evidence['records'][0]
    assert record['answer'] == row['details']['faqs'][0]['answer']
    assert record['source_url'] == row['source_url']
    assert record['steps'] and all('房东' not in s for s in record['steps'])


def test_no_detail_button_when_legacy_answer_has_no_more_content(legacy_catalog):
    legacy_catalog('Singapore', steps=[])
    result = knowledge.answer(None, 'Singapore', '公交怎么买票？')
    assert result['choices'] == []
    expanded = knowledge.answer(None, 'Singapore', '公交怎么买票？请详细说明')
    assert '没有更多' in expanded['reply'] and '步骤' in expanded['reply']


def test_missing_knowledge_has_no_grounding_evidence(monkeypatch):
    monkeypatch.setattr(knowledge.repository, 'iter_life_knowledge', lambda *_: [])
    result = knowledge.answer(None, 'Singapore', '公交怎么买票？')
    assert not result.get('reply_evidence')


def test_detailed_answer_does_not_inherit_a_concise_modifier(legacy_catalog):
    legacy_catalog('Singapore')
    brief = knowledge.answer(None, 'Singapore', '只用一句话告诉我，公交怎么买票？')
    detail = knowledge.answer(None, 'Singapore', brief['choices'][0]['query'])
    assert detail['reply_evidence']['depth'] == 'detailed'
    assert '\n' in detail['reply'] and '同一张卡片' in detail['reply']


def test_detail_after_payment_followup_does_not_duplicate_country(legacy_catalog):
    legacy_catalog('Singapore')
    history = [{'role': 'user', 'content': '新加坡公交怎么坐？'}]
    result = knowledge.answer(None, 'Singapore', '那怎么付钱？', history=history)
    choice = result['choices'][0]['query']
    assert choice.count('新加坡') == 1 and '付钱' in choice


def test_external_knowledge_includes_the_reviewed_legacy_steps(legacy_catalog, monkeypatch):
    from app.core.config import get_settings
    from app.modules.student.schemas import KnowledgeRetrievalRequest
    from pydantic import SecretStr
    legacy_catalog('Singapore')
    monkeypatch.setattr(get_settings(), 'stu_knowledge_token', SecretStr('local-test-token'))
    request = KnowledgeRetrievalRequest(knowledge_id='Singapore', query='公交怎么买票？')
    result = knowledge.external_retrieval(None, request, 'local-test-token')
    assert '适用范围及余额' in result['records'][0]['content']
    assert '房东' not in result['records'][0]['content']
