"""Strict local portal/RBAC acceptance. Login writes sessions/audit, not business data.
Use --health-only explicitly for readiness without login. Full mode requires all
four fixture roles; custom expected grants may be supplied with --expectations.
All issued tokens are logged out in finally and are never printed.
"""
import argparse
from dataclasses import dataclass, field
import json
import sys
from pathlib import Path
from urllib.parse import urlsplit
import httpx

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
API='http://127.0.0.1:8002'
CREDENTIALS=ROOT/'logs/ent-portal-local-credentials.json'
REQUIRED_ROLES=('admin','employee','manager','team_leader')

class VerificationError(Exception):
    pass

@dataclass(frozen=True)
class Account:
    username:str
    role:str
    password:str=field(repr=False)


def credentials_from_file(file):
    if not file.exists():raise VerificationError('缺少凭据文件；完整验收必须提供四角色账号，单独探活请使用 --health-only')
    try:payload=json.loads(file.read_text(encoding='utf-8'))
    except (OSError,ValueError):raise VerificationError('凭据文件不可读或JSON格式不正确') from None
    rows=payload.get('accounts') if isinstance(payload,dict) else None
    if not isinstance(rows,list):raise VerificationError('凭据文件必须含 accounts 数组')
    accounts=[]
    for role in REQUIRED_ROLES:
        matches=[a for a in rows if isinstance(a,dict) and a.get('role')==role]
        if len(matches)!=1:raise VerificationError('角色 '+role+' 必须有且仅有一套测试账号')
        row=matches[0]
        if not isinstance(row.get('username'),str) or not row['username'].strip():raise VerificationError('角色 '+role+' 缺少账号')
        if not isinstance(row.get('password'),str) or not row['password']:raise VerificationError('角色 '+role+' 缺少密码')
        accounts.append(Account(row['username'],role,row['password']))
    if len({a.username for a in accounts})!=len(accounts):raise VerificationError('四角色必须使用不同账号')
    return accounts


def expected_grants(file=None):
    from app.core.security.rbac import ROLE_DEFAULTS,PERMISSIONS
    if file:
        try:values=json.loads(file.read_text(encoding='utf-8'))
        except (OSError,ValueError):raise VerificationError('预期权限文件不可读或JSON格式错误') from None
    else:values={r:sorted(ROLE_DEFAULTS[r]) for r in REQUIRED_ROLES}
    if not isinstance(values,dict):raise VerificationError('预期权限文件必须是角色到权限数组的对象')
    result={}
    for role in REQUIRED_ROLES:
        grants=values.get(role)
        if not isinstance(grants,list) or not all(isinstance(x,str) for x in grants) or len(set(grants))!=len(grants):
            raise VerificationError('角色 '+role+' 的预期权限必须是无重复的字符串数组')
        if not set(grants)<=set(PERMISSIONS):raise VerificationError('预期权限中包含未注册的权限')
        if 'dashboard:read' not in grants:raise VerificationError('本验收的四个工作台角色必须具有 dashboard:read')
        result[role]=set(grants)
    return result


def envelope(response,label):
    if response.status_code!=200:raise VerificationError(label+' 预期HTTP200，实际'+str(response.status_code))
    try:body=response.json()
    except ValueError:raise VerificationError(label+' 响应不是JSON') from None
    if not isinstance(body,dict) or type(body.get('code')) is not int or body['code']!=0 or 'data' not in body:
        raise VerificationError(label+' 响应缺少成功业务码或data')
    return body['data']


def profile(data,account,grants,label,expected_id=None):
    if not isinstance(data,dict):raise VerificationError(label+' 缺少用户对象')
    uid=data.get('id')
    if type(uid) is not int or uid<1 or (expected_id is not None and uid!=expected_id):raise VerificationError(label+' 员工身份不一致')
    if data.get('username')!=account.username or data.get('role_code')!=account.role:raise VerificationError(label+' 登录账号/实际角色不一致')
    actual=data.get('permissions')
    if not isinstance(actual,list) or not all(isinstance(x,str) for x in actual) or len(set(actual))!=len(actual) or set(actual)!=grants:
        raise VerificationError(label+' 权限集合与预期配置不一致')
    return uid


def verify(client,api=API,credentials=CREDENTIALS,health_only=False,expectations=None):
    from app.modules.portal.service import FEATURES
    api=api.rstrip('/')
    url=urlsplit(api)
    if url.scheme!='http' or url.hostname not in ('127.0.0.1','localhost','::1') or url.path or url.query or url.fragment or url.username:
        raise VerificationError('本脚本仅向明确配置的本机API发送联调凭据')
    report={'api':api,'scope':'auth-readiness' if health_only else 'four-role-rbac','status':'running','checks':[],'cleanup':[]}
    tokens=[];failure=None
    try:
        status=envelope(client.get(api+'/api/v1/auth/status'),'认证就绪')
        if not isinstance(status,dict) or status.get('mode')!='trusted_jwt' or status.get('ready') is not True:
            raise VerificationError('认证未就绪：需trusted_jwt、有效签名配置及已初始化认证表')
        report['checks'].append({'name':'auth_ready','passed':True})
        if not health_only:
            accounts=credentials_from_file(credentials);expected=expected_grants(expectations)
            profiles={}
            for account in accounts:
                data=envelope(client.post(api+'/api/v1/auth/login',json={'username':account.username,'password':account.password}),account.role+' 登录')
                if not isinstance(data,dict) or not isinstance(data.get('access_token'),str) or not data['access_token'].strip():
                    raise VerificationError(account.role+' 登录未返回有效token')
                token=data['access_token'];tokens.append((account.role,token))
                headers={'Authorization':'Bearer '+token}
                uid=profile(data.get('user'),account,expected[account.role],account.role+' 登录')
                me=envelope(client.get(api+'/api/v1/auth/me',headers=headers),account.role+' /me')
                profile(me,account,expected[account.role],account.role+' /me',uid)
                ctx=envelope(client.get(api+'/api/v1/portal/context',headers=headers),account.role+' 工作台')
                if not isinstance(ctx,dict):raise VerificationError(account.role+' 工作台响应格式错误')
                profile(ctx.get('user'),account,expected[account.role],account.role+' 工作台身份',uid)
                features=ctx.get('features')
                if not isinstance(features,list) or not all(isinstance(f,dict) for f in features):raise VerificationError(account.role+' 菜单格式错误')
                wanted={path:(key,permission) for key,_title,path,permission in FEATURES if permission in expected[account.role]}
                actual={f.get('path'):(f.get('key'),f.get('permission')) for f in features}
                if len(actual)!=len(features) or actual!=wanted:raise VerificationError(account.role+' 菜单集合与权限目录不一致')
                profiles[account.role]=me
                report['checks'].append({'name':'identity_permissions_features','role':account.role,'passed':True,
                    'permissions':len(expected[account.role]),'features':sorted(wanted)})
            if len({p['id'] for p in profiles.values()})!=4:raise VerificationError('四角色返回了重复员工身份')
            employee_id=profiles['employee']['id']
            guards=[('/api/v1/auth/users','users:manage'),('/api/v1/auth/roles','roles:manage'),
                    ('/api/v1/auth/audit','audit:read'),('/api/v1/consultant/leads','crm:read'),
                    ('/api/v1/student-admin/leaves/pending','leaves:read'),('/api/v1/portal/students','scores:read'),
                    ('/api/v1/enterprise/colleagues/'+str(employee_id)+'/contact','directory:contacts')]
            for role,token in tokens:
                headers={'Authorization':'Bearer '+token}
                # A 401 here is an identity failure, never an RBAC success.
                envelope(client.get(api+'/api/v1/auth/me',headers=headers),role+' guard前身份检查')
                for endpoint,permission in guards:
                    expected_status=200 if permission in expected[role] else 403
                    response=client.get(api+endpoint,headers=headers)
                    if response.status_code!=expected_status:
                        raise VerificationError(role+' '+endpoint+' 预期HTTP'+str(expected_status)+'，实际'+str(response.status_code))
                    if expected_status==200:envelope(response,role+' '+endpoint)
                    report['checks'].append({'name':'api_permission','role':role,'permission':permission,'expected':expected_status,'actual':response.status_code,'passed':True})
            report['verified_roles']=list(REQUIRED_ROLES)
    except (VerificationError,httpx.HTTPError) as exc:
        failure=str(exc) if isinstance(exc,VerificationError) else 'API连接失败或超时，请检查本机门户服务'
    finally:
        for role,token in tokens:
            headers={'Authorization':'Bearer '+token}
            try:
                result=envelope(client.post(api+'/api/v1/auth/logout',headers=headers),role+' logout')
                if not isinstance(result,dict) or result.get('logged_out') is not True:raise VerificationError('未确认退出')
                revoked=client.get(api+'/api/v1/auth/me',headers=headers)
                if revoked.status_code!=401:raise VerificationError('退出后token未返回401')
                report['cleanup'].append({'role':role,'logged_out':True,'revoked_status':401})
            except (VerificationError,httpx.HTTPError):
                report['cleanup'].append({'role':role,'logged_out':False})
                failure=failure or '至少一个测试登录会话未能完成退出/失效核验'
    report['status']='failed' if failure else 'passed'
    if failure:report['error']=failure
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--api',default=API)
    p.add_argument('--credentials',type=Path,default=CREDENTIALS)
    p.add_argument('--expectations',type=Path,help='显式四角色预期权限JSON；默认使用ROLE_DEFAULTS')
    p.add_argument('--health-only',action='store_true',help='仅探活，不代表登录/RBAC验收')
    p.add_argument('--output',type=Path)
    args=p.parse_args(argv)
    try:
        with httpx.Client(trust_env=False,timeout=10,follow_redirects=False) as client:
            report=verify(client,args.api,args.credentials,args.health_only,args.expectations)
    except VerificationError as exc:
        report={'scope':'auth-readiness' if args.health_only else 'four-role-rbac','status':'failed','error':str(exc)}
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if report['status']!='passed':print('FAIL: '+report['error'],file=sys.stderr)
    return 0 if report['status']=='passed' else 1

if __name__=='__main__':raise SystemExit(main())
