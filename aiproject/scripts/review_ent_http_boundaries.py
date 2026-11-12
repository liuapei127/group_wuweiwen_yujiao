"""Read current OpenAPI and exercise every endpoint against the normal blocked app.
No identity overrides, no credentials. All business requests must be rejected.
"""
import argparse,json
from pathlib import Path
import httpx
from sqlalchemy import MetaData
from app.core.database import engine
from scripts.local_ent_validation import snapshot,preserve_existing
ROOT=Path(__file__).resolve().parents[1]
p=argparse.ArgumentParser();p.add_argument('--output',default='docs/回复Cursor/runs/ent-http-full-review-2026-11-12.json');args=p.parse_args()
ids=json.loads((ROOT/'data/datasets/ent-local-verify-v1-manifest.json').read_text(encoding='utf-8'))['ids']
a,s=ids['employee_a'],ids['student_a']
body={
 ('POST','/api/v1/consultant/leads'):{'customer_name':'ENT_REVIEW_NO_WRITE','owner_employee_id':a},
 ('PATCH','/api/v1/consultant/leads/{lead_id}'):{'remark':'ENT_REVIEW_NO_WRITE'},
 ('PATCH','/api/v1/consultant/leads/{lead_id}/status'):{'status':'contacting'},
 ('POST','/api/v1/consultant/leads/{lead_id}/follow-ups'):{'employee_id':a,'content':'ENT_REVIEW_NO_WRITE'},
 ('POST','/api/v1/employee-reports'):{'employee_id':a,'content':'ENT_REVIEW_NO_WRITE'},
 ('POST','/api/v1/student-admin/leaves/{leave_id}/approve'):{'approver_id':a,'decision':'approved'},
 ('POST','/api/v1/enterprise/onboarding-guides'):{'title':'ENT_REVIEW_NO_WRITE','category':'test','content':'Synthetic verification only'},
 ('POST','/api/v1/enterprise/scores'):{'student_id':s,'course_name':'ENT_REVIEW_NO_WRITE','score':'88.00'},
 ('PUT','/api/v1/enterprise/scores/{score_id}'):{'student_id':s,'course_name':'ENT_REVIEW_NO_WRITE','score':'88.00','expected_version':1},
 ('PATCH','/api/v1/enterprise/tickets/{ticket_id}'):{'expected_status':'pending','status':'processing'},
 ('POST','/api/v1/enterprise/todos'):{'title':'ENT_REVIEW_NO_WRITE'},
 ('PATCH','/api/v1/enterprise/todos/{todo_id}'):{'expected_status':'pending','status':'done'},
 ('POST','/api/v1/enterprise/commands'):{'action':'update_lead_status_by_name','params':{'customer_name':'ENT_REVIEW_NO_WRITE','status':'contacting'}},
 ('POST','/api/v1/ai/nl2sql/query'):{'intent':'leads_by_status','params':{'status':'new'}},
}
values={'lead_id':ids['lead_0'],'employee_id':a,'score_id':ids['score_0'],'ticket_id':ids['ticket_0'],'todo_id':ids['todo_0'],'leave_id':ids['leave_0']}
metadata=MetaData();metadata.reflect(engine)
with engine.connect() as conn:before=snapshot(conn,metadata)
results=[]
with httpx.Client(base_url='http://127.0.0.1:8000',trust_env=False,timeout=15) as client:
 schema=client.get('/openapi.json').json()
 guard=client.get('/api/v1/consultant/leads')
 if guard.status_code!=503:raise RuntimeError('Normal app is not blocked; refusing live write probes')
 for route,ops in schema['paths'].items():
  for method in ops:
   if method not in ('get','post','put','patch','delete'):continue
   upper=method.upper();url=route.format(**values)
   params={}
   if route.endswith('/organizations/colleagues'):params['name']='验证顾问'
   if route=='/api/v1/enterprise/scores' and method=='get':params['student_id']=s
   kwargs={'params':params}
   if upper in ('POST','PUT','PATCH'):
    if (upper,route) not in body:raise RuntimeError('No safe fixture for '+upper+' '+route)
    kwargs['json']=body[(upper,route)]
   r=client.request(upper,url,**kwargs)
   expected=200 if route in ('/health','/health/db') else 503
   results.append({'method':upper,'path':route,'status':r.status_code,'expected':expected,'body':r.json(),'passed':r.status_code==expected})
 for header in ({'X-Employee-Id':'1'},{'X-Employee-Id':str(a)},{'Authorization':'Bearer ent-review-invalid-token'}):
  r=client.get('/api/v1/consultant/leads',headers=header)
  results.append({'case':'forged identity rejected','headers':header,'status':r.status_code,'expected':503,'passed':r.status_code==503})
with engine.connect() as conn:
 preserve_existing(conn,metadata,before)
 after=snapshot(conn,metadata)
 assert {k:set(v) for k,v in before.items()}=={k:set(v) for k,v in after.items()}
report={'transport':'real TCP normal app.main','openapi_operations':len(results)-3,'tests':results,'database_unchanged':True,'passed':sum(r['passed'] for r in results),'total':len(results)}
(ROOT/args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in report.items() if k!='tests'},ensure_ascii=False))
if report['passed']!=report['total']:raise SystemExit(1)
