"""Only the backend can call Dify; employee JWTs never leave this backend."""
from urllib.parse import urlsplit
import httpx
from app.core.config import get_settings
from app.core.exceptions import BusinessError

class DifyIntentClient:
    def extract(self,text,pending):
        s=get_settings();key=s.dify_workflow_api_key.get_secret_value()
        if not key:raise BusinessError(503,'AI尚未配置，请先配置服务端Dify工作流')
        try:
            with httpx.Client(trust_env=False,timeout=httpx.Timeout(s.dify_timeout_seconds,connect=5)) as client:
                response=client.post(s.dify_api_url.rstrip('/')+'/workflows/run',headers={'Authorization':'Bearer '+key},
                    json={'inputs':{'query':text,'pending':pending},'response_mode':'blocking','user':'ent-portal-intent'})
            if response.status_code!=200:raise BusinessError(502,'Dify参数理解服务暂不可用，未执行业务操作')
            data=response.json().get('data',{})
            if data.get('status')!='succeeded':raise BusinessError(502,'AI工作流未完成，未执行业务操作')
            extracted=data.get('outputs',{}).get('text')
            if not isinstance(extracted,str):raise BusinessError(502,'AI返回格式不正确，未执行业务操作')
            return extracted
        except (httpx.HTTPError,ValueError):
            raise BusinessError(502,'AI服务连接失败或超时，未执行业务操作') from None


def call_business(method,planned_url,body,employee_token):
    s=get_settings();base=s.assistant_api_url.rstrip('/')
    target=urlsplit(base);planned=urlsplit(planned_url)
    if target.scheme!='http' or target.hostname not in ('127.0.0.1','localhost') or target.path or target.query or target.fragment:
        raise BusinessError(503,'业务回调地址必须配置为本机API')
    if planned.scheme!='http' or planned.netloc!='host.docker.internal:8000' or not planned.path.startswith('/api/v1/'):
        raise BusinessError(422,'AI请求地址不在允许范围')
    url=base+planned.path+('?' + planned.query if planned.query else '')
    try:
        with httpx.Client(trust_env=False,timeout=httpx.Timeout(15,connect=3),follow_redirects=False) as client:
            response=client.request(method.upper(),url,headers={'Authorization':'Bearer '+employee_token,'Content-Type':'application/json'},
                content=body.encode('utf-8') if method!='get' else None)
        return response.status_code,response.text
    except httpx.HTTPError:
        return 0,''
