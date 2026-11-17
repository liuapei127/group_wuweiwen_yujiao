"""Verified emergency cards never substitute study destination for current location."""
from app.modules.student.assistant_safety_resources import cards_for


def context(country=None, **extra):
    return {'active': True, 'source': 'current_conversation_user_statements',
            'self_reported_location': {'country': country, 'label': {'US': '纽约', 'Germany': '德国', 'Singapore': '新加坡'}.get(country, '其他地区')}, **extra}


def test_unknown_current_location_does_not_use_academic_destination():
    assert cards_for({'active': True, 'source': 'current_conversation_user_statements',
                      'student_context': {'profile': {'abroad_country': 'Germany'}}}) == []


def test_only_current_conversation_context_may_select_resources():
    assert cards_for(context('US', source='assistant_generated')) == []
    assert cards_for(context('Germany', active=False)) == []
    assert cards_for(context('unsupported')) == []


def test_new_york_overrides_academic_destination_without_model_inventing_number():
    state = context('US', student_context={'profile': {'abroad_country': 'Germany'}})
    cards = cards_for(state)
    assert len(cards) == 1
    assert cards[0]['source_url'].startswith('https://www.nyc.gov/')
    assert any('911' in f['value'] for f in cards[0]['fields'])
    assert not any('112' in f['value'] for f in cards[0]['fields'])
    assert any('自述' in f['label'] for f in cards[0]['fields'])


def test_germany_and_singapore_share_verified_visible_help_contract():
    for code,number,domain in [('Germany','112','gesund.bund.de'),('Singapore','995','www.scdf.gov.sg')]:
        [card] = cards_for(context(code))
        assert domain in card['source_url']
        assert any(number in f['value'] for f in card['fields'])
        assert any('立即危险' in f['value'] for f in card['fields'])
        assert all('已联系' not in f['value'] for f in card['fields'])


def test_callers_cannot_mutate_shared_verified_resource_catalog():
    a=cards_for(context('US'));a[0]['fields'][0]['value']='changed'
    b=cards_for(context('US'))
    assert b[0]['fields'][0]['value']!='changed'
