"""Test the existing WebApp using ordinary HTTP/SSE; passports stay in memory."""
import argparse,json,time,uuid
from pathlib import Path
import requests
p=argparse.ArgumentParser();p.add_argument('--site-code',required=True);p.add_argument('--cases',required=True);p.add_argument('--output',default='/tmp/ent-published-repair-results.json');a=p.parse_args()
cases=json.loads(Path(a.cases).read_text(encoding='utf-8'))
s=requests.Session();s.trust_env=False
headers={'X-App-Code':a.site_code}
r=s.get('http://nginx/api/passport',headers=headers,params={'user_id':'ent-review-'+uuid.uuid4().hex},timeout=20);r.raise_for_status()
headers['X-App-Passport']=r.json()['access_token']
results=[];conversations={}
for case in cases:
 started=time.monotonic();task_id=None
 result={**case,'transport':'existing public Dify WebApp HTTP/SSE','events':[]}
 print('ENT_REVIEW_PROGRESS '+case['id'],flush=True)
 try:
  payload={'inputs':{},'query':case['query'],'response_mode':'streaming','files':[]}
  group=case.get('conversation_key')
  if group in conversations:payload['conversation_id']=conversations[group]
  with s.post('http://nginx/api/chat-messages',headers=headers,json=payload,stream=True,timeout=(10,45)) as response:
   result['http_status']=response.status_code
   if response.status_code!=200:result['body']=response.text[:1000]
   else:
    for raw in response.iter_lines():
     if time.monotonic()-started>70:raise TimeoutError('Review case exceeded 70 seconds')
     line=raw.decode('utf-8')
     if not line.startswith('data:'):continue
     data=json.loads(line[5:].strip());result['events'].append(data)
     task_id=data.get('task_id') or task_id
     if group and data.get('conversation_id'):conversations[group]=data['conversation_id']
     if data.get('event') in ('error','message_end'):break
 except Exception as exc:
  result.update(error_type=type(exc).__name__,error=str(exc))
  if task_id:
   try:result['stop_status']=s.post('http://nginx/api/chat-messages/'+task_id+'/stop',headers=headers,json={},timeout=10).status_code
   except requests.RequestException:result['stop_status']='request_failed'
 events=result['events']
 answer=''.join(e.get('answer','') if e.get('event') in ('message','agent_message') else e.get('data',{}).get('text','') if e.get('event')=='text_chunk' else '' for e in events)
 nodes=[e.get('data',{}) for e in events if e.get('event')=='node_finished']
 calls=[n for n in nodes if n.get('node_id','').startswith('http_')]
 expected=case.get('expect_http',False)
 # This WebApp redacts node outputs and omits workflow_finished. Verify those
 # from persisted records separately; never invent a terminal workflow status.
 end=next((e for e in events if e.get('event')=='message_end'),{})
 result.update(answer=answer,message_id=end.get('id'),conversation_id=end.get('conversation_id'),workflow_run_id=next((e.get('workflow_run_id') for e in events if e.get('workflow_run_id')),None),verification_scope='stream transport and visible nodes only; persisted run/intent checked separately',checks={'http_200':result.get('http_status')==200,'message_end':bool(end),'no_stream_error':not result.get('error') and not any(e.get('event')=='error' for e in events),'expected_answer':case.get('expect','') in answer,'business_call_count':len(calls)==int(expected)})
 result['public_stream_passed']=all(result['checks'].values());result['elapsed']=round(time.monotonic()-started,2)
 results.append(result);Path(a.output).write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
 print('ENT_REVIEW_RESULT '+json.dumps({k:result[k] for k in ('id','checks','public_stream_passed','elapsed')},ensure_ascii=False),flush=True)
if not all(r['public_stream_passed'] for r in results):raise SystemExit(1)
