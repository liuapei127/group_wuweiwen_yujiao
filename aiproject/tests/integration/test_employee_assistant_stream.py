import json
from datetime import datetime
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.ai.assistant import service
from app.core.security import EmployeePrincipal
from app.modules.auth import service as auth_service
from app.modules.consultant.models import CrmLead
from tests.integration.test_ent_portal_routes import isolated_portal


def test_employee_assistant_streams_details_preserves_json_and_rechecks_history(isolated_portal,monkeypatch):
    app,engine=isolated_portal('trusted_jwt')
    permissions={'ai:use','todos:read'}
    monkeypatch.setattr(auth_service.AuthService,'authenticate',lambda self,token:EmployeePrincipal(10,frozenset(permissions)))
    monkeypatch.setattr(service.DifyIntentClient,'extract',lambda self,*args,**kwargs:'{"intent":"todos","params":{"due_only":true}}')
    calls=[]
    def execute(method,url,body,token):
        calls.append((method,url,token))
        return 200,json.dumps({'code':0,'data':[{'id':378,'title':'待处理投诉','status':'pending',
            'priority':'medium','due_time':'2026-11-18T10:16:22','related_id':271}]})
    monkeypatch.setattr(service,'call_business',execute)
    headers={'Authorization':'Bearer employee-test'}
    try:
        with TestClient(app) as client:
            base='/api/v1/ai/assistant/conversations'
            cid=client.post(base,headers=headers,json={'title':'流式测试'}).json()['data']['id']
            result=client.post(f'{base}/{cid}/messages',headers={**headers,'Accept':'text/event-stream'},
                               json={'text':'查询我的到期待办','expected_version':0})
            assert result.headers['content-type'].startswith('text/event-stream')
            events=[]
            for part in result.text.split('\n\n'):
                if 'data: ' in part:
                    events.append((part.splitlines()[0],json.loads(part.split('data: ',1)[1])))
            chunks=[data['text'] for event,data in events if event=='event: text']
            saved=events[-1][1]['data']
            assert chunks and '待办编号：378' in chunks[-1]
            assert '到期时间：2026-11-18 10:16:22' in chunks[-1]
            assert saved['messages'][-1]['content']==chunks[-1]
            assert len(calls)==1 and calls[0][2]=='employee-test'
            assert client.get(f'{base}/{cid}',headers=headers).json()['data']['messages'][-1]['content']==chunks[-1]
            # The original JSON client remains supported and an ordinary greeting never executes business APIs.
            plain=client.post(f'{base}/{cid}/messages',headers=headers,json={'text':'你好','expected_version':1})
            assert plain.headers['content-type'].startswith('application/json') and len(calls)==1
            permissions.remove('todos:read')
            history=client.get(f'{base}/{cid}',headers=headers).json()['data']['messages']
            assert history[1]['content']=='当前账号没有查看这条业务结果的权限。'
    finally:
        engine.dispose()


def test_employee_assistant_routes_name_to_owned_customer_before_colleague_search(isolated_portal, monkeypatch):
    app, engine = isolated_portal('trusted_jwt')
    permissions = frozenset({'ai:use', 'crm:read', 'directory:read'})
    actors = {
        'owner': EmployeePrincipal(10, permissions),
        'other': EmployeePrincipal(11, permissions),
        'no-crm': EmployeePrincipal(10, permissions - {'crm:read'}),
    }
    monkeypatch.setattr(auth_service.AuthService, 'authenticate', lambda self, token: actors[token])
    model_calls = []

    def extract(self, text, *args, **kwargs):
        model_calls.append(text)
        return json.dumps({'intent': 'colleagues', 'params': {'name': '林晓宁'}})

    monkeypatch.setattr(service.DifyIntentClient, 'extract', extract)
    try:
        with Session(engine) as db:
            now = datetime(2026, 11, 18)
            db.add(CrmLead(id=1187, customer_name='林晓宁', owner_employee_id=10, create_time=now, update_time=now))
            db.commit()

        with TestClient(app) as client:
            def execute(method, url, body, token):
                assert method == 'get'
                route = urlsplit(url)
                if route.path.endswith('/organizations/colleagues'):
                    return 200, json.dumps({'code': 0, 'data': []})
                assert route.path == '/api/v1/consultant/leads/1187'
                response = client.get(route.path, headers={'Authorization': 'Bearer ' + token})
                return response.status_code, response.text

            monkeypatch.setattr(service, 'call_business', execute)
            base = '/api/v1/ai/assistant/conversations'

            def send(token, text):
                headers = {'Authorization': 'Bearer ' + token}
                cid = client.post(base, headers=headers, json={'title': '查客户'}).json()['data']['id']
                response = client.post(f'{base}/{cid}/messages', headers=headers, json={'text': text, 'expected_version': 0})
                assert response.status_code == 200
                return response.json()['data']['messages'][-1]

            customer = send('owner', '查询一下林晓宁')
            assert customer['metadata']['action'] == 'lead_detail'
            assert '客户姓名：林晓宁' in customer['content']
            assert send('owner', '查看我的客户林晓宁的资料')['metadata']['action'] == 'lead_detail'
            assert send('owner', '查询同事林晓宁')['metadata']['action'] == 'colleagues'
            assert send('other', '查询一下林晓宁')['metadata']['action'] == 'colleagues'
            assert send('owner', '查询客户列表')['metadata']['action'] == 'colleagues'
            assert send('owner', '查看我的客户资料')['metadata']['action'] == 'colleagues'
            assert send('owner', '查询客户跟进记录')['metadata']['action'] == 'colleagues'
            assert '当前名下没有查到' in send('other', '查询客户林晓宁')['content']
            assert send('no-crm', '查询客户林晓宁')['metadata']['error_status'] == 403
            assert model_calls == ['查询同事林晓宁', '查询一下林晓宁', '查询客户列表', '查看我的客户资料', '查询客户跟进记录']
    finally:
        engine.dispose()
