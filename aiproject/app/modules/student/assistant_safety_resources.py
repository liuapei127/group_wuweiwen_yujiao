"""Reviewed emergency resources selected only from a current conversation self-report.

This is a fixed, dated reference catalog, not a search/contact tool. It cannot
locate the student, place a call, or infer location from academic destination.
"""
from copy import deepcopy

_CATALOG = {
    'US': {'title': '美国紧急求助', 'number': '911', 'service': '警察、消防或医疗急救',
           'source': '纽约市政府 · Emergency services',
           'url': 'https://www.nyc.gov/main/your-government/contact-nyc-government?locale=en'},
    'Germany': {'title': '德国紧急求助', 'number': '112', 'service': '危及生命时的紧急救援',
                'source': '德国联邦健康门户 · Notfallnummern',
                'url': 'https://gesund.bund.de/notfallnummern/'},
    'Singapore': {'title': '新加坡紧急求助', 'number': '995', 'service': '紧急医疗救护',
                  'source': '新加坡民防部队 · Emergency Medical Services',
                  'url': 'https://www.scdf.gov.sg/home/about-scdf/emergency-medical-services'},
}


def cards_for(safety_context):
    state = safety_context or {}
    if not state.get('active') or state.get('source') != 'current_conversation_user_statements':
        return []
    location = state.get('self_reported_location')
    if not isinstance(location, dict):
        return []
    item = _CATALOG.get(location.get('country'))
    if item is None:
        return []
    label = str(location.get('label') or location.get('country') or '')[:100]
    return deepcopy([{'title': item['title'], 'fields': [
        {'label': '你本次自述的所在地', 'value': label},
        {'label': '适用情况', 'value': '如有立即危险、已经受伤或无法保证自身安全，请联系当地紧急服务，或请身边的人帮助联系。'},
        {'label': '紧急服务', 'value': item['number'] + ' · ' + item['service']},
        {'label': '说明位置', 'value': '向接线人员说明当前具体地址或附近地标，并说明你需要立即帮助。'},
        {'label': '官方来源', 'value': item['source']},
        {'label': '核对日期', 'value': '2026-11-17'},
    ], 'source_url': item['url']}])
