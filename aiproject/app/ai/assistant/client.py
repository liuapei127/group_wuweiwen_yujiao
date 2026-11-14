"""Only the backend can call Dify; employee JWTs never leave this backend."""
from secrets import token_hex
from urllib.parse import urlsplit
import httpx
from app.core.config import get_settings
from app.core.exceptions import BusinessError

class DifyIntentClient:
    def extract(self, text, pending):
        settings = get_settings()
        chat_key = settings.dify_ent_chatflow_api_key.get_secret_value()
        workflow_key = settings.dify_workflow_api_key.get_secret_value()
        if not (chat_key or workflow_key):
            raise BusinessError(503, 'AI尚未配置，请先配置服务端Dify工作流')

        payload = {'response_mode': 'blocking'}
        if chat_key:
            endpoint = '/chat-messages'
            payload.update(inputs={'pending': pending or ''}, query=text, user='ent-' + token_hex(16))
        else:
            endpoint = '/workflows/run'
            payload.update(inputs={'query': text, 'pending': pending}, user='ent-portal-intent')

        try:
            with httpx.Client(trust_env=False, timeout=httpx.Timeout(settings.dify_timeout_seconds, connect=5)) as client:
                response = client.post(
                    settings.dify_api_url.rstrip('/') + endpoint,
                    headers={'Authorization': 'Bearer ' + (chat_key or workflow_key)}, json=payload,
                )
            response.raise_for_status()
            result = response.json()
        except (httpx.HTTPError, ValueError):
            raise BusinessError(502, 'AI服务连接失败或超时，未执行业务操作') from None

        if chat_key:
            extracted = result.get('answer') if isinstance(result, dict) else None
            if isinstance(extracted, str) and extracted.strip() in {'ENT_BACKEND_UNAVAILABLE', 'ENT_MODEL_UNAVAILABLE'}:
                raise BusinessError(502, '企业助手暂不可用，未执行业务操作')
        else:
            data = result.get('data', {}) if isinstance(result, dict) else {}
            if not isinstance(data, dict) or data.get('status') != 'succeeded':
                raise BusinessError(502, 'AI工作流未完成，未执行业务操作')
            outputs = data.get('outputs')
            extracted = outputs.get('text') if isinstance(outputs, dict) else None
        if not isinstance(extracted, str) or not extracted.strip():
            raise BusinessError(502, 'AI返回格式不正确，未执行业务操作')
        return extracted


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
