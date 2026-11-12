"""Verifier regressions: no network, production database or real credentials."""
import json
import httpx
import pytest
from scripts import verify_ent_portal_http as smoke
from app.core.security.rbac import ROLE_DEFAULTS
from app.modules.portal.service import FEATURES

class Portal:
    def __init__(self):
        self.grants={r:set(ROLE_DEFAULTS[r]) for r in smoke.REQUIRED_ROLES}
        self.active=set();self.logins=[];self.logouts=[]
        self.empty_permissions=False;self.empty_features=False;self.denial=403
        self.missing_token=False;self.wrong_identity=False;self.logout_failure=False;self.ready=True
        self.bad_context_code=False
    def handle(self,request):
        route=request.url.path
        token=request.headers.get('Authorization','').removeprefix('Bearer ')
        role=token.removeprefix('test-token-')
        def ok(data):return httpx.Response(200,json={'code':0,'data':data})
        def profile(r):return {'id':1 if self.wrong_identity else smoke.REQUIRED_ROLES.index(r)+1,
            'username':'test_'+r,'role_code':r,'permissions':[] if self.empty_permissions else sorted(self.grants[r])}
        if route.endswith('/status'):return ok({'mode':'trusted_jwt','ready':self.ready})
        if route.endswith('/login'):
            r=json.loads(request.content)['username'].removeprefix('test_');self.logins.append(r)
            if self.missing_token:return ok({'user':profile(r)})
            self.active.add(r)
            return ok({'access_token':'test-token-'+r,'user':profile(r)})
        if role not in self.active:return httpx.Response(401,json={'detail':'expired'})
        if route.endswith('/logout'):
            if self.logout_failure:return httpx.Response(500,json={'detail':'failure'})
            self.active.remove(role);self.logouts.append(role);return ok({'logged_out':True})
        if route.endswith('/me'):return ok(profile(role))
        if route.endswith('/context'):
            if self.bad_context_code:return httpx.Response(200,json={'code':1,'data':{}})
            features=[] if self.empty_features else [{'key':k,'title':t,'path':p,'permission':g} for k,t,p,g in FEATURES if g in self.grants[role]]
            return ok({'user':profile(role),'features':features})
        permission={
            '/api/v1/auth/users':'users:manage','/api/v1/auth/roles':'roles:manage','/api/v1/auth/audit':'audit:read',
            '/api/v1/consultant/leads':'crm:read','/api/v1/student-admin/leaves/pending':'leaves:read',
            '/api/v1/portal/students':'scores:read','/api/v1/enterprise/colleagues/2/contact':'directory:contacts'}[route]
        return ok([]) if permission in self.grants[role] else httpx.Response(self.denial,json={'detail':'denied'})

@pytest.fixture
def setup(tmp_path):
    portal=Portal();file=tmp_path/'credentials.json'
    file.write_text(json.dumps({'accounts':[{'username':'test_'+r,'role':r,'password':'synthetic-password'} for r in smoke.REQUIRED_ROLES]}),encoding='utf-8')
    with httpx.Client(transport=httpx.MockTransport(portal.handle)) as client:
        yield portal,file,client

def test_default_four_roles_guard_matrix_and_logout(setup):
    p,f,c=setup;report=smoke.verify(c,credentials=f)
    assert report['status']=='passed'
    assert report['verified_roles']==list(smoke.REQUIRED_ROLES)
    assert len([x for x in report['checks'] if x['name']=='api_permission'])==28
    assert len(p.logins)==4 and len(p.logouts)==4 and not p.active
    assert all(x['revoked_status']==401 for x in report['cleanup'])
    assert 'test-token-' not in json.dumps(report) and 'synthetic-password' not in json.dumps(report)

@pytest.mark.parametrize('kind',['file_missing','role_missing','password_missing','duplicate_role'])
def test_missing_prerequisites_fail_instead_of_skipping(setup,kind):
    p,f,c=setup
    if kind=='file_missing':f=f.parent/'absent.json'
    else:
        payload=json.loads(f.read_text())
        if kind=='role_missing':payload['accounts'].pop()
        if kind=='password_missing':payload['accounts'][0].pop('password')
        if kind=='duplicate_role':payload['accounts'].append(payload['accounts'][0])
        f.write_text(json.dumps(payload))
    report=smoke.verify(c,credentials=f)
    assert report['status']=='failed' and not p.logins

@pytest.mark.parametrize('flag',['empty_permissions','empty_features','missing_token','wrong_identity','bad_context_code'])
def test_wrong_profile_or_features_are_not_accepted(setup,flag):
    p,f,c=setup;setattr(p,flag,True)
    assert smoke.verify(c,credentials=f)['status']=='failed'
    assert not p.active

def test_401_is_not_an_rbac_denial_success(setup):
    p,f,c=setup;p.denial=401
    report=smoke.verify(c,credentials=f)
    assert report['status']=='failed' and '预期HTTP403，实际401' in report['error']
    assert len(p.logouts)==4 and not p.active

def test_logout_failure_fails_acceptance(setup):
    p,f,c=setup;p.logout_failure=True
    report=smoke.verify(c,credentials=f)
    assert report['status']=='failed' and any(not x['logged_out'] for x in report['cleanup'])

def test_explicit_health_only_does_not_claim_rbac(setup):
    p,f,c=setup
    report=smoke.verify(c,credentials=f.parent/'absent',health_only=True)
    assert report['status']=='passed' and report['scope']=='auth-readiness'
    assert 'verified_roles' not in report and not p.logins

def test_explicit_custom_role_expectations(setup):
    p,f,c=setup;p.grants['employee'].add('directory:contacts')
    expected=f.parent/'expectations.json';expected.write_text(json.dumps({r:sorted(g) for r,g in p.grants.items()}))
    assert smoke.verify(c,credentials=f,expectations=expected)['status']=='passed'

def test_cli_returns_nonzero_for_missing_credentials(setup,monkeypatch,capsys):
    p,f,c=setup
    monkeypatch.setattr(smoke.httpx,'Client',lambda **kwargs:type(c)(transport=httpx.MockTransport(p.handle),**kwargs))
    assert smoke.main(['--credentials',str(f.parent/'missing')])==1
    assert 'FAIL:' in capsys.readouterr().err

def test_nonlocal_target_rejected_before_credentials(setup):
    p,f,c=setup
    with pytest.raises(smoke.VerificationError,match='本机API'):
        smoke.verify(c,api='https://example.invalid',credentials=f)
    assert not p.logins
