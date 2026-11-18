import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import EmployeePrincipal
from app.modules.auth import service as auth_service
from app.modules.consultant.customer_models import CustomerIdentity
from app.modules.profile.models import CustomerSource
from app.modules.visitor import router as visitor_router
from tests.integration.test_ent_portal_routes import isolated_portal


@pytest.fixture(autouse=True)
def isolated_registration_capacity(monkeypatch):
    monkeypatch.setattr(visitor_router, '_AUTH_CAPACITY', visitor_router.CsChatCapacity(4, 2, 10))


@pytest.mark.parametrize('uploader', ['employee', 'visitor', 'material'])
@pytest.mark.parametrize('identity', ['', '姓名：测试客户\n', '本人手机号：13900007390\n'])
def test_partial_identity_and_ownership_confirmation(isolated_portal, monkeypatch, uploader, identity):
    app, engine = isolated_portal('trusted_jwt')
    permissions = frozenset({'visitor-intake:read', 'visitor-intake:write', 'crm:read', 'crm:write'})
    monkeypatch.setattr(auth_service.AuthService, 'authenticate', lambda self, token: EmployeePrincipal(
        20 if token == 'other' else 10, frozenset() if token == 'no-read' else permissions))
    employee = {'Authorization': 'Bearer owner'}
    public = '/api/v1/visitors/customer-profile'
    try:
        with TestClient(app) as client:
            signup = client.post('/api/v1/visitors/register', json={
                'username': '13900007390', 'password': 'Test!9876', 'name': '测试客户',
            })
            assert signup.status_code == 201
            visitor = {'Authorization': 'Bearer ' + signup.json()['data']['access_token']}
            visitor_id = client.get('/api/v1/consultant/visitor-intake/pending', headers=employee).json()['data'][0]['visitor_id']
            claim = client.post(f'/api/v1/consultant/visitor-intake/{visitor_id}/claim', headers=employee)
            lead_id = claim.json()['data']['crm_lead_id']
            detail = f'/api/v1/consultant/leads/{lead_id}'
            endpoint, headers = (public, visitor) if uploader == 'visitor' else (detail, employee)
            document = identity + '家庭经济状况：30-50万\n语言能力：雅思6分'
            source_id = None
            if uploader == 'material':
                material = client.post('/api/v1/visitor/materials', headers=visitor,
                    files={'file': ('语言证书.txt', document.encode())})
                assert material.status_code == 201
                source_id = material.json()['data']['source_id']
                response = client.post(f'{detail}/materials/{source_id}/imports/preview', headers=employee)
            else:
                response = client.post(endpoint + '/imports/preview', headers=headers,
                    files={'file': ('语言证书.txt', document.encode())})
            assert response.status_code == 200, response.text
            preview = response.json()['data']
            assert preview['ownership_confirmation_required'] is (not identity)
            assert preview['matches'] == ([identity.split('：')[0]] if identity else [])
            before = client.get(public, headers=visitor).json()['data']
            assert before['family_finance'] is None
            assert before['language_ability'] is None
            payload = {'preview_id': preview['preview_id'], 'expected_version': preview['version'],
                       'fields': ['family_finance', 'language_ability']}
            if source_id is not None:
                payload['source_id'] = source_id
            other_endpoint, other_headers = (detail, employee) if uploader == 'visitor' else (public, visitor)
            assert client.post(other_endpoint + '/imports/confirm', headers=other_headers,
                               json={**payload, 'ownership_confirmed': True}).status_code == 404
            if not identity:
                for invalid in ({}, {'ownership_confirmed': False}, {'ownership_confirmed': 'false'}):
                    assert client.post(endpoint + '/imports/confirm', headers=headers, json={**payload, **invalid}).status_code == 422
                assert client.get(public, headers=visitor).json()['data']['version'] == before['version']
                payload['ownership_confirmed'] = True
            confirmed = client.post(endpoint + '/imports/confirm', headers=headers, json=payload)
            assert confirmed.status_code == 200, confirmed.text
            customer = client.get(detail + '/profile', headers=employee).json()['data']
            website = client.get(public, headers=visitor).json()['data']
            assert customer['family_finance'] == website['family_finance'] == '30-50万'
            assert customer['language_ability'] == website['language_ability'] == '雅思6分'
            assert customer['screening_input'] == website['screening_input']
            assert client.post(endpoint + '/imports/confirm', headers=headers, json=payload).status_code == 409
            with Session(engine) as db:
                source = db.scalar(select(CustomerSource).where(CustomerSource.lead_id == lead_id))
                assert source.file_name == '语言证书.txt'
                assert source.parse_result['ownership']['basis'] == ('matched_identity' if identity else 'uploader_confirmation')
                assert source.parse_result['ownership']['confirmed_by_kind'] == ('visitor' if uploader == 'visitor' else 'employee')
                assert source.parse_result['ownership']['confirmed_by_id'] == (visitor_id if uploader == 'visitor' else 10)
                assert source.parse_result['ownership']['confirmed_at']
                if source_id is not None:
                    assert source.id == source_id
                imported_id = source.id
            assert customer['imports'] == website['imports']
            assert customer['imports'][0]['id'] == imported_id
            for base, auth in ((detail, employee), (public, visitor)):
                source_url = f'{base}/imports/{imported_id}'
                viewed = client.get(source_url, headers=auth)
                assert viewed.status_code == 200, viewed.text
                assert viewed.json()['data']['raw_content'] == document
                assert viewed.json()['data']['has_attachment'] is True
                assert viewed.headers['cache-control'] == 'no-store'
                original = client.get(source_url + '/attachment', headers=auth)
                assert original.status_code == 200
                assert original.content == document.encode()
                assert original.headers['cache-control'] == 'no-store'
                assert original.headers['x-content-type-options'] == 'nosniff'
                assert client.get(source_url).status_code == 401
            for suffix in ('', '/attachment'):
                assert client.get(f'{detail}/imports/{imported_id}{suffix}',
                    headers={'Authorization': 'Bearer other'}).status_code == 404
                assert client.get(f'{detail}/imports/{imported_id}{suffix}',
                    headers={'Authorization': 'Bearer no-read'}).status_code == 403
                assert client.get(f'{public}/imports/{imported_id + 1000}{suffix}', headers=visitor).status_code == 404
    finally:
        engine.dispose()


def test_identity_is_rechecked_when_confirming_preview(isolated_portal, monkeypatch):
    app, engine = isolated_portal('trusted_jwt')
    principal = EmployeePrincipal(10, frozenset({'crm:read', 'crm:write', 'visitor-intake:read', 'visitor-intake:write'}))
    monkeypatch.setattr(auth_service.AuthService, 'authenticate', lambda self, token: principal)
    employee = {'Authorization': 'Bearer owner'}
    try:
        with TestClient(app) as client:
            assert client.post('/api/v1/visitors/register', json={
                'username': '13900007391', 'password': 'Test!9876', 'name': '原客户姓名',
            }).status_code == 201
            visitor_id = client.get('/api/v1/consultant/visitor-intake/pending', headers=employee).json()['data'][0]['visitor_id']
            claim = client.post(f'/api/v1/consultant/visitor-intake/{visitor_id}/claim', headers=employee)
            lead_id = claim.json()['data']['crm_lead_id']
            endpoint = f'/api/v1/consultant/leads/{lead_id}'
            response = client.post(endpoint + '/imports/preview', headers=employee,
                files={'file': ('资料.txt', '姓名：原客户姓名\n年龄：22'.encode())})
            assert response.status_code == 200
            preview = response.json()['data']
            with Session(engine) as db:
                from app.core.security.credentials import utc_now
                db.add(CustomerIdentity(lead_id=lead_id, verified_name='核实后的另一姓名',
                    verified_mobile='13900007391', verified_by=10, verified_at=utc_now()))
                db.commit()
            response = client.post(endpoint + '/imports/confirm', headers=employee, json={
                'preview_id': preview['preview_id'], 'expected_version': preview['version'],
                'fields': ['age'], 'ownership_confirmed': True,
            })
            assert response.status_code == 422
            assert client.get(endpoint + '/profile', headers=employee).json()['data']['age'] is None
    finally:
        engine.dispose()


def test_imported_files_are_scoped_to_the_customer_and_support_old_text_records(isolated_portal, monkeypatch):
    from app.modules.profile.models import ParseStatus, SourceType

    app, engine = isolated_portal('trusted_jwt')
    principal = EmployeePrincipal(10, frozenset({'crm:read', 'crm:write', 'visitor-intake:read', 'visitor-intake:write'}))
    monkeypatch.setattr(auth_service.AuthService, 'authenticate', lambda self, token: principal)
    employee = {'Authorization': 'Bearer owner'}
    public = '/api/v1/visitors/customer-profile'
    try:
        with TestClient(app) as client:
            visitors = []
            for index in range(2):
                signup = client.post('/api/v1/visitors/register', json={
                    'username': f'1390000740{index}', 'password': 'Test!9876', 'name': f'测试客户{index}',
                })
                visitors.append({'Authorization': 'Bearer ' + signup.json()['data']['access_token']})
            pending = client.get('/api/v1/consultant/visitor-intake/pending', headers=employee).json()['data']
            leads = [client.post(f'/api/v1/consultant/visitor-intake/{row["visitor_id"]}/claim', headers=employee)
                     .json()['data']['crm_lead_id'] for row in pending]
            with Session(engine) as db:
                source = CustomerSource(lead_id=leads[0], source_type=SourceType.text,
                    raw_content='历史资料正文', parse_status=ParseStatus.success,
                    parse_result={'customer_id': leads[0], 'confirmed_fields': {'age': 22}})
                pending_source = CustomerSource(lead_id=leads[0], source_type=SourceType.text,
                    raw_content='未导入的内容', parse_status=ParseStatus.pending)
                db.add_all([source, pending_source])
                db.commit()
                source_id, pending_id = source.id, pending_source.id
            detail = f'/api/v1/consultant/leads/{leads[0]}'
            own_list = client.get(public, headers=visitors[0]).json()['data']['imports']
            assert [item['id'] for item in own_list] == [source_id]
            original = client.get(f'{public}/imports/{source_id}', headers=visitors[0])
            assert original.json()['data']['raw_content'] == '历史资料正文'
            assert original.json()['data']['has_attachment'] is False
            assert client.get(f'{public}/imports/{source_id}/attachment', headers=visitors[0]).status_code == 404
            for suffix in ('', '/attachment'):
                assert client.get(f'{public}/imports/{source_id}{suffix}', headers=visitors[1]).status_code == 404
                assert client.get(f'/api/v1/consultant/leads/{leads[1]}/imports/{source_id}{suffix}', headers=employee).status_code == 404
                assert client.get(f'{detail}/imports/{pending_id}{suffix}', headers=employee).status_code == 404
    finally:
        engine.dispose()
