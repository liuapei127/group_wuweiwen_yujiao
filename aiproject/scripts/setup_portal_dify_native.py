"""Run in Dify API. Create the owner-authorized private portal intent workflow.
The generated app-scoped key is written only to a private file, never stdout.
"""
from gevent import monkey
monkey.patch_all()
import psycogreen.gevent as pg
from grpc.experimental import gevent as grpc_gevent
grpc_gevent.init_gevent();pg.patch_psycopg()
import json,os,sys
os.chdir('/app/api');sys.path.insert(0,'/app/api')
print('ENT_PORTAL_DIFY initializing',flush=True)
from app import app
from extensions.ext_database import db
from sqlalchemy import select
from sqlalchemy.orm import Session
from models import App,Account
from models.model import ApiToken,ApiTokenType
from services.app_service import AppService,CreateAppParams
from services.workflow_service import WorkflowService
package=json.load(open('/tmp/ent_portal_intent.json',encoding='utf-8'))
with app.test_request_context('/console/authorized-ent-portal-setup',method='POST'):
 with Session(db.engine,expire_on_commit=False) as session:
  existing=session.get(App,'ac18cfb8-3f60-406f-99dd-d9cc635dc71f')
  if existing is None:raise RuntimeError('Existing ENT app missing')
  account=session.get(Account,existing.created_by);account.set_tenant_id_with_session(existing.tenant_id,session=session)
  if account.current_tenant_id!=existing.tenant_id or str(account.role) not in ('owner','admin'):raise RuntimeError('Owner/admin workspace membership is required')
  target=session.scalar(select(App).where(App.tenant_id==existing.tenant_id,App.name=='ENT门户-参数理解',App.mode=='workflow'))
  if target is None:
   target=AppService().create_app(existing.tenant_id,CreateAppParams(name='ENT门户-参数理解',mode='workflow',description=package['app']['description'],icon_type='emoji',icon='🤖',icon_background='#DFF4EE',max_active_requests=4),account,session=session)
  target.enable_site=False;target.enable_api=True
  service=WorkflowService();draft=service.get_draft_workflow(app_model=target,session=session)
  synced=service.sync_draft_workflow(app_model=target,graph=package['workflow']['graph'],features={},unique_hash=draft.unique_hash if draft else None,
   account=account,environment_variables=[],conversation_variables=[],session=session)
  published=service.publish_workflow(session=session,app_model=target,account=account,marked_name='门户参数理解v1',marked_comment='仅提取参数，业务JWT不会传入Dify；权限和确认由可信后端处理')
  session.flush();target.workflow_id=published.id;session.commit()
  token=session.scalar(select(ApiToken).where(ApiToken.app_id==target.id,ApiToken.type==ApiTokenType.APP))
  if token is None:
   token=ApiToken(app_id=target.id,tenant_id=target.tenant_id,type=ApiTokenType.APP,
                  token=ApiToken.generate_api_key('app-',24,session=session))
   session.add(token);session.commit()
  secret={'app_id':target.id,'workflow_id':published.id,'api_key':token.token}
  with open('/tmp/ent-portal-dify-secret.json','w',encoding='utf-8') as handle:json.dump(secret,handle,ensure_ascii=False)
  os.chmod('/tmp/ent-portal-dify-secret.json',0o600)
  print('ENT_PORTAL_DIFY_RESULT '+json.dumps({'app_id':target.id,'workflow_id':published.id,'nodes':3,'enable_site':target.enable_site,'enable_api':target.enable_api,'token_created_or_reused':True},ensure_ascii=False),flush=True)
