"""Run inside the existing Dify API container using its application execution service.
Only the explicitly selected app/workflow is exercised. Does not edit graphs,
publish versions, create credentials, or change ENT identity configuration.
"""
from gevent import monkey
monkey.patch_all()
import psycogreen.gevent as psycogreen_gevent
from grpc.experimental import gevent as grpc_gevent
grpc_gevent.init_gevent()
psycogreen_gevent.patch_psycopg()
print("ENT_REVIEW_PROGRESS starting application",flush=True)
import os,sys,json,time,argparse
os.chdir('/app/api');sys.path.insert(0,'/app/api')
from app import app
print("ENT_REVIEW_PROGRESS application initialized",flush=True)
from extensions.ext_database import db
from sqlalchemy.orm import Session
from sqlalchemy import select
from models import App,Account,Message
from models.workflow import WorkflowRun,WorkflowNodeExecutionModel
from services.app_generate_service import AppGenerateService
from core.app.entities.app_invoke_entities import InvokeFrom

parser=argparse.ArgumentParser()
parser.add_argument('--app-id',required=True)
parser.add_argument('--workflow-id',required=True)
parser.add_argument('--cases',required=True)
parser.add_argument('--draft',action='store_true')
parser.add_argument('--recheck')
parser.add_argument('--public-recheck')
parser.add_argument('--output',default='/tmp/ent-repair-draft-results.json')
args=parser.parse_args()
cases=json.load(open(args.cases,encoding='utf-8'))
results=[]
conversations={}
previous={row['case_id']:row for row in json.load(open(args.recheck,encoding='utf-8'))} if args.recheck else {}
if args.public_recheck:
    for row in json.load(open(args.public_recheck,encoding='utf-8')):
        previous[row['id']]={'response':{'id':row.get('message_id'),'conversation_id':row.get('conversation_id'),'answer':row.get('answer','')},'public_stream_passed':row.get('public_stream_passed',False)}
for case in cases:
    print('ENT_REVIEW_PROGRESS case '+case['id'],flush=True)
    started=time.monotonic()
    result={'case_id':case['id'],'query':case['query'],'workflow_id':args.workflow_id,'execution':'Dify AppGenerateService, blocking, owner workspace context'}
    try:
        with app.test_request_context('/console/ent-review',method='POST'):
            with Session(db.engine,expire_on_commit=False) as session:
                target=session.get(App,args.app_id)
                if target is None:raise RuntimeError('Target application missing')
                account=session.get(Account,target.created_by)
                account.set_tenant_id_with_session(target.tenant_id,session=session)
                if account.current_tenant_id!=target.tenant_id:raise RuntimeError('Owner is not a workspace member')
                payload={'query':case['query'],'inputs':{},'files':[],'auto_generate_name':False}
                if not args.draft:payload['workflow_id']=args.workflow_id
                group=case.get('conversation_key')
                conversation_id=case.get('conversation_id') or conversations.get(group)
                if conversation_id:payload['conversation_id']=conversation_id
                response=previous[case['id']]['response'] if (args.recheck or args.public_recheck) else AppGenerateService.generate(app_model=target,user=account,args=payload,invoke_from=InvokeFrom.DEBUGGER,session=session,streaming=False)
                result['response']=response
                result['completed']=True
                if group and response.get('conversation_id'):conversations[group]=response['conversation_id']
                message=session.get(Message,response.get('id'))
                run=session.get(WorkflowRun,message.workflow_run_id) if message and message.workflow_run_id else None
                result['workflow_status']=str(run.status) if run else 'not_recorded'
                traces=list(session.scalars(select(WorkflowNodeExecutionModel).where(WorkflowNodeExecutionModel.workflow_run_id==run.id).order_by(WorkflowNodeExecutionModel.index))) if run else []
                result['node_trace']=[{'node_id':n.node_id,'status':str(n.status),'error':n.error,'outputs':n.outputs_dict} for n in traces if n.node_id in ('health','gate','plan') or n.node_id.startswith('http_') or str(n.status) not in ('succeeded',)]
                calls=[n for n in result['node_trace'] if n['node_id'].startswith('http_')]
                plan_node=next((n['outputs'] for n in result['node_trace'] if n['node_id']=='plan'),{}) or {}
                try:pending=json.loads(plan_node.get('pending') or '{}')
                except ValueError:pending={}
                expected_http=case.get('expect_http',False)
                status_ok=result['workflow_status']=='succeeded'
                if expected_http and result['workflow_status']=='partial-succeeded':
                    non_success=[n for n in result['node_trace'] if n['status']!='succeeded']
                    status_ok=bool(non_success) and all(n['node_id'].startswith('http_') and 'status code 503' in (n['error'] or '') and (n['outputs'] or {}).get('error_type')=='HTTPResponseCodeError' and (n['outputs'] or {}).get('error_message')==n['error'] for n in non_success)
                result['checks']={'workflow_version':bool(run) and str(run.workflow_id)==args.workflow_id,'public_stream':previous.get(case['id'],{}).get('public_stream_passed',True),'terminal_or_expected_handled_503':status_ok,'answer':case.get('expect','') in response.get('answer',''),'business_call_count':len(calls)==int(expected_http),'intent':not case.get('expect_intent') or plan_node.get('intent')==case['expect_intent'],'pending_intent':not case.get('expect_pending_intent') or pending.get('intent')==case['expect_pending_intent']}
                if args.public_recheck:result['execution']='ordinary public WebApp HTTP/SSE plus read-only persisted node verification'
                result['passed']=all(result['checks'].values())
    except Exception as exc:
        result.update(completed=False,error_type=type(exc).__name__,error=str(exc))
    result['duration_seconds']=round(time.monotonic()-started,2)
    results.append(result)
    open(args.output,'w',encoding='utf-8').write(json.dumps(results,ensure_ascii=False,indent=2,default=str))
    print('ENT_REVIEW_RESULT '+json.dumps(result,ensure_ascii=False,default=str),flush=True)

if not all(row.get('passed',False) for row in results):raise SystemExit(1)
