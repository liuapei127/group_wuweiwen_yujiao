import json
import logging
from app.core.exceptions import BusinessError
from app.core.security.rbac import ACTION_PERMISSIONS, INTENT_PERMISSIONS
from app.core.security.authorization import require_permission
from app.ai.workflows.ent_contracts import plan,format_result,CONFIRM,CANCEL,parse_action
from .repository import AssistantRepository
from .client import DifyIntentClient,call_business

logger=logging.getLogger(__name__)

class AssistantService:
    def __init__(self,db,extractor=None,executor=None):
        self.db=db;self.repo=AssistantRepository(db)
        self.extractor=extractor or DifyIntentClient()
        self.executor=executor or call_business

    def create(self,body,p):
        cid=self.repo.create(p.employee_id,body.title);self.db.commit()
        return self.detail(cid,p)

    def list(self,p):return self.repo.list(p.employee_id)

    def detail(self,cid,p):
        row=self.repo.get(cid,p.employee_id)
        if not row:raise BusinessError(404,'对话不存在')
        try:pending=json.loads(row['pending']) if row['pending'] else None
        except ValueError:pending=None
        return {'id':row['id'],'title':row['title'],'version':row['version'],'pending':pending,
                'messages':self.repo.history(cid)}

    def send(self,cid,body,p,employee_token):
        old=self.repo.get(cid,p.employee_id)
        if not old:raise BusinessError(404,'对话不存在')
        nonce=self.repo.reserve(cid,p.employee_id,body.expected_version)
        if not nonce:
            self.db.rollback();raise BusinessError(409,'对话已更新或正在处理，请刷新后重试；不要重复确认')
        self.db.commit()
        version=body.expected_version+1
        pending='';metadata={'source':'Dify','executed':False}
        text=body.text.strip()
        try:
            # Exact confirmations and cancellations are owned by server state, not an LLM.
            if text.rstrip('。！! ') in CONFIRM|CANCEL:
                model_text='';metadata['source']='服务端确认状态机'
            else:
                model_text=self.extractor.extract(text,old['pending'])
                try:
                    extracted=parse_action(model_text)
                    if extracted.get('intent')=='daily_submit':
                        for key in ('key_progress','risks'):
                            value=extracted['params'].get(key)
                            if isinstance(value,str):extracted['params'][key]=[s.strip() for s in value.splitlines() if s.strip()]
                        model_text=json.dumps(extracted,ensure_ascii=False)
                except (ValueError,TypeError):
                    pass
            output=plan(model_text,text,old['pending'])
            pending=output['pending']
            requested=output['intent']
            if pending:
                requested=json.loads(pending).get('intent',requested)
            if requested in ACTION_PERMISSIONS:
                require_permission(p,ACTION_PERMISSIONS[requested])
            if output['call_api'] and output['intent']=='nl_query':
                query=json.loads(output['http_body'])
                require_permission(p,INTENT_PERMISSIONS[query['intent']])
            metadata.update(action=requested,method=output['method'].upper() if output['call_api'] else None)
            reply=output['reply']
            if output['call_api']:
                status,result=self.executor(output['method'],output['http_url'],output['http_body'],employee_token)
                metadata.update(executed=True,http_status=status,action=output['intent'])
                reply=format_result(status,result,output['intent'])['reply']
        except BusinessError as exc:
            reply=exc.detail+'。未确认任何业务修改。'
            metadata.update(error_status=exc.status_code)
            pending='' if text.rstrip('。！! ') in CONFIRM else old['pending']
        except Exception:
            logger.exception('AI turn failed; conversation=%s',cid)
            reply='处理过程中出现错误，未确认操作成功；如已提交请先查询核对，不会自动重复提交。'
            metadata.update(error_status=500)
            pending=''
        try:
            if not self.repo.finish(cid,p.employee_id,version,nonce,pending,text,reply,metadata):
                self.db.rollback();raise BusinessError(409,'对话状态已变化，请刷新核对结果')
            self.db.commit()
        except Exception:
            self.db.rollback();raise
        return self.detail(cid,p)
