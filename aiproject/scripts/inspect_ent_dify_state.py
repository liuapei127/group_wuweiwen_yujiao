"""Read only the chosen app's published/draft structure; no secrets in output."""
from gevent import monkey
monkey.patch_all()
import psycogreen.gevent as pg
from grpc.experimental import gevent as grpc_gevent
grpc_gevent.init_gevent();pg.patch_psycopg()
import os,sys,json,hashlib
os.chdir('/app/api');sys.path.insert(0,'/app/api')
from app import app
from extensions.ext_database import db
from sqlalchemy.orm import Session
from sqlalchemy import select
from models import App
from models.workflow import Workflow
with app.app_context(),Session(db.engine) as session:
 target=session.get(App,'ac18cfb8-3f60-406f-99dd-d9cc635dc71f')
 published=session.get(Workflow,target.workflow_id)
 draft=session.scalar(select(Workflow).where(Workflow.app_id==target.id,Workflow.version=='draft'))
 def summary(workflow):
  graph=workflow.graph_dict
  return {'id':workflow.id,'nodes':len(graph['nodes']),'edges':len(graph['edges']),'graph_sha256':hashlib.sha256(json.dumps(graph,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'environment_variable_names':[v.name for v in workflow.environment_variables],'conversation_variable_names':[v.name for v in workflow.conversation_variables]}
 result={'app_id':target.id,'published':summary(published),'draft':summary(draft),'old_published_retained':session.get(Workflow,'b1fa9a00-e642-47c7-ad29-dee0dc7b1b93') is not None,'published_draft_graph_equal':published.graph_dict==draft.graph_dict}
 print('ENT_STATE '+json.dumps(result,ensure_ascii=False),flush=True)
