"""Only the backend can call Dify; employee JWTs never leave this backend."""
import json
import re
from datetime import datetime, timedelta, timezone
from secrets import token_hex
from urllib.parse import urlsplit
import httpx
from app.ai.dify_stream import ChatAnswer
from app.core.config import get_settings
from app.core.exceptions import BusinessError


_CHAT_REPLY = re.compile(r'^\s*(?:\x60{3}(?:json)?\s*)?\{\s*"intent"\s*:\s*"chat"\s*,\s*"params"\s*:\s*\{\s*\}\s*,\s*"reply"\s*:\s*"')
_JSON_TEXT = re.compile(r'(?:[^"\\\x00-\x1f]|\\(?:["\\/bfnrt]|u[0-9a-fA-F]{4}))*')


def chat_preview(text):
    """Extract only a chat reply from the classifier's partial JSON."""
    text = re.sub(r'^\s*<think>.*?</think>\s*', '', text, flags=re.S)
    start = _CHAT_REPLY.match(text)
    if not start:
        return ""
    fragment = _JSON_TEXT.match(text, start.end()).group()
    decoded = json.loads('"' + fragment + '"')
    # A UTF-16 surrogate can arrive one token before the rest of the character.
    return decoded.encode("utf-16", "surrogatepass").decode("utf-16", "ignore").strip()[:1600]


class DifyIntentClient:
    def extract(self, text, pending, history, on_text=None):
        settings = get_settings()
        chat_key = settings.dify_ent_chatflow_api_key.get_secret_value()
        workflow_key = settings.dify_workflow_api_key.get_secret_value()
        if not (chat_key or workflow_key):
            raise BusinessError(503, 'AI尚未配置，请先配置服务端Dify工作流')

        today = datetime.now(timezone(timedelta(hours=8))).date().isoformat()
        payload = {'response_mode': 'blocking'}
        if chat_key:
            endpoint = '/chat-messages'
            payload.update(inputs={'pending': pending or '', 'today': today, 'chat_history': history},
                           query=text, user='ent-' + token_hex(16))
        else:
            endpoint = '/workflows/run'
            payload.update(inputs={'query': text, 'pending': pending, 'today': today, 'chat_history': history},
                           user='ent-portal-intent')

        try:
            with httpx.Client(trust_env=False, timeout=httpx.Timeout(settings.dify_timeout_seconds, connect=5)) as client:
                url = settings.dify_api_url.rstrip('/') + endpoint
                headers = {'Authorization': 'Bearer ' + (chat_key or workflow_key)}
                if on_text:
                    reader = self._stream if chat_key else self._workflow_stream
                    result = reader(client, url, headers, payload, on_text)
                else:
                    response = client.post(url, headers=headers, json=payload)
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


    @staticmethod
    def _stream(client, url, headers, payload, on_text):
        answer = ChatAnswer()
        last = ""
        with client.stream("POST", url, headers=headers, json={**payload, "response_mode": "streaming"}) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if answer.accept(line):
                    visible = chat_preview(answer.text)
                    if visible != last:
                        last = visible
                        on_text(visible)
                if answer.finished and not answer.waiting_for_workflow:
                    break
        return answer.response()


    @staticmethod
    def _workflow_stream(client, url, headers, payload, on_text):
        text, last = '', ''
        with client.stream('POST', url, headers=headers, json={**payload, 'response_mode': 'streaming'}) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line.startswith('data:'):
                    continue
                event = json.loads(line[5:].strip())
                if not isinstance(event, dict):
                    raise ValueError('Invalid workflow stream')
                data = event.get('data') or {}
                if event.get('event') == 'error':
                    raise ValueError('Workflow failed')
                if event.get('event') == 'workflow_finished':
                    if not isinstance(data, dict) or data.get('status') != 'succeeded':
                        raise ValueError('Workflow did not succeed')
                    return {'data': data}
                if event.get('event') == 'text_chunk' and isinstance(data, dict):
                    chunk = data.get('text')
                    if not isinstance(chunk, str):
                        continue
                    text += chunk
                    if len(text) > 100_000:
                        raise ValueError('Workflow answer exceeded the limit')
                    visible = chat_preview(text)
                    if visible != last:
                        last = visible
                        on_text(visible)
        raise ValueError('Workflow stream ended prematurely')


def call_business(method,planned_url,body,employee_token):
    s=get_settings();base=s.assistant_api_url.rstrip('/')
    target=urlsplit(base);planned=urlsplit(planned_url)
    if target.scheme!='http' or target.hostname not in ('127.0.0.1','localhost') or target.path or target.query or target.fragment:
        raise BusinessError(503,'业务回调地址必须配置为本机API')
    if planned.scheme!='http' or planned.netloc!='host.docker.internal:8000' or not planned.path.startswith('/api/v1/'):
        raise BusinessError(422,'AI请求地址不在允许范围')
    url=base+planned.path+('?' + planned.query if planned.query else '')
    try:
        timeout = httpx.Timeout(s.dify_timeout_seconds + 5 if planned.path == '/api/v1/reporting/employee-reports/formal-summary' else 15, connect=3)
        with httpx.Client(trust_env=False, timeout=timeout, follow_redirects=False) as client:
            response=client.request(method.upper(),url,headers={'Authorization':'Bearer '+employee_token,'Content-Type':'application/json'},
                content=body.encode('utf-8') if method!='get' else None)
        return response.status_code,response.text
    except httpx.HTTPError:
        return 0,''
