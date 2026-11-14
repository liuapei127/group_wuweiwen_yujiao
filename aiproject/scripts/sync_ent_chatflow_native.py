"""Run inside Dify API: use the owner's normal workflow service, no new credentials.
Draft is saved first. --publish is an explicit final action after validation.
"""
from gevent import monkey
monkey.patch_all()
import psycogreen.gevent as pg
from grpc.experimental import gevent as grpc_gevent
grpc_gevent.init_gevent();pg.patch_psycopg()
import argparse,json,os,sys,time
os.chdir('/app/api');sys.path.insert(0,'/app/api')
print('ENT_SYNC_PROGRESS initializing',flush=True)
from app import app
from extensions.ext_database import db
from sqlalchemy.orm import Session
from models import App,Account
from factories import variable_factory
from services.workflow_service import WorkflowService
p=argparse.ArgumentParser();p.add_argument('--app-id',required=True);p.add_argument('--package',required=True);p.add_argument('--publish',action='store_true');a=p.parse_args()
package=json.load(open(a.package,encoding='utf-8'))['workflow']
with app.test_request_context('/console/ent-authorized-repair',method='POST'):
 with Session(db.engine,expire_on_commit=False) as session:
  target=session.get(App,a.app_id)
  if target is None:raise RuntimeError('Target app missing')
  account=session.get(Account,target.created_by)
  account.set_tenant_id_with_session(target.tenant_id,session=session)
  if account.current_tenant_id!=target.tenant_id or str(account.role) not in ('owner','admin'):raise RuntimeError('An owner/admin workspace context is required')
  service=WorkflowService();draft=service.get_draft_workflow(app_model=target,session=session)
  before={'published_id':target.workflow_id,'draft_id':draft.id,'graph':draft.graph_dict,'features':draft.features_dict}
  open('/tmp/ent-before-sync-'+time.strftime('%Y%m%d-%H%M%S')+'-'+str(os.getpid())+'.json','x',encoding='utf-8').write(json.dumps(before,ensure_ascii=False,indent=2))
  features=draft.features_dict
  for name in ('opening_statement','suggested_questions','speech_to_text'):
   if name in package['features']:
    features[name]=package['features'][name]
  cv=[variable_factory.build_conversation_variable_from_mapping(v) for v in package['conversation_variables']]
  ev=[v for v in draft.environment_variables if v.name!='employee_id']
  synced=service.sync_draft_workflow(app_model=target,graph=package['graph'],features=features,unique_hash=draft.unique_hash,account=account,environment_variables=ev,conversation_variables=cv,session=session)
  session.commit()
  result={'draft_id':synced.id,'old_published_id':before['published_id'],'nodes':len(package['graph']['nodes']),'published':False}
  if a.publish:
   published=service.publish_workflow(session=session,app_model=target,account=account,marked_name='ENT工作台集成',marked_comment='同步工作台意图目录，权限、数据查询、候选和写入确认由业务后端执行')
   session.flush();target.workflow_id=published.id;target.updated_by=account.id;session.commit()
   result.update(published=True,published_id=published.id)
  print('ENT_SYNC_RESULT '+json.dumps(result,ensure_ascii=False),flush=True)
