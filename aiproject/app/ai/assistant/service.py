import json
import logging
import re
from app.core.exceptions import BusinessError
from app.core.security.rbac import ACTION_PERMISSIONS, INTENT_PERMISSIONS
from app.core.security.authorization import require_permission
from app.ai.workflows.ent_contracts import plan,CONFIRM,CANCEL,parse_action,selected_id
from app.modules.consultant.errors import ConflictError
from app.modules.consultant.repository import ConsultantRepository
from app.modules.statistics.service import current_report_members
from .repository import AssistantRepository
from .replies import business_reply, chat_history, conversational_reply, display_stored_reply
from .client import DifyIntentClient,call_business
from app.modules.feedback.repository import FeedbackRepository

logger=logging.getLogger(__name__)

_CUSTOMER_NAME_LOOKUP = re.compile(
    r"(?:请|帮我)?\s*(?:查询|查看|查找|查)(?:一下)?\s*(?:(?P<customer>(?:我(?:的|名下的))?客户)\s*)?"
    r"(?P<name>[\u3400-\u9fff·]{2,16}?)(?P<details>的(?:资料|档案|详情))?[。！!？?]*"
)
_NON_CUSTOMER_PREFIXES = (
    "同事", "员工", "老师", "学生", "班级", "联系人", "通知", "待办", "日报", "周报", "组织", "工单", "成绩", "请假",
)
_NON_CUSTOMER_NAMES = (
    "列表", "名单", "资料", "档案", "详情", "信息", "状态", "跟进", "记录",
    "数量", "总数", "情况", "线索", "统计", "报表", "明细", "清单", "全部", "所有", "客户",
)

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
        if not isinstance(pending, dict):
            pending = None
        if pending:
            permission = ACTION_PERMISSIONS.get(pending.get('intent'))
            if permission and permission not in p.permissions:
                pending = None
        messages=self.repo.history(cid)
        for message in messages:
            meta = message['metadata']
            if meta.get('action') in ('tickets', 'ticket_detail', 'ticket_update') and 200 <= meta.get('http_status', 0) < 300:
                ids = meta.get('feedback_ticket_ids')
                if (not isinstance(ids, list) or 'tickets:read' not in p.permissions
                        or not set(ids).issubset(FeedbackRepository(self.db).visible_ids(p, ids))):
                    message['content'] = '这条工单结果当前不可查看，请按当前权限重新查询。'
                    # Do not reformat the original stored result after redaction.
                    message['scope_unavailable'] = True
            meta.pop('feedback_ticket_ids', None)
        for message in messages:
            permission = ACTION_PERMISSIONS.get(message['metadata'].get('action'))
            if permission and permission not in p.permissions:
                message['content'] = '当前账号没有查看这条业务结果的权限。'
            elif not message.get('scope_unavailable'):
                message['content'] = display_stored_reply(message)
        scoped=[message for message in messages if 'report_employee_ids' in message['metadata']]
        if scoped:
            try:
                members=current_report_members(self.db,p)
            except BusinessError:
                members=set()
            for message in scoped:
                if members is not None and not set(message['metadata']['report_employee_ids']).issubset(members):
                    message['content']='当前权限范围已变更，无法查看这条日报查询结果。'
                message['metadata'].pop('report_employee_ids')
        return {'id':row['id'],'title':row['title'],'version':row['version'],'pending':pending,'messages':messages}

    def send(self,cid,body,p,employee_token,on_text=None):
        old=self.repo.get(cid,p.employee_id)
        if not old:raise BusinessError(404,'对话不存在')
        nonce=self.repo.reserve(cid,p.employee_id,body.expected_version)
        if not nonce:
            self.db.rollback();raise BusinessError(409,'对话已更新或正在处理，请刷新后重试；不要重复确认')
        self.db.commit()
        version=body.expected_version+1
        pending='';metadata={'source':'Dify','executed':False}
        text=body.text.strip()
        reply = conversational_reply(text, p.permissions)
        try:
            if reply is not None:
                pending = old['pending'] or ''
                metadata['source'] = '服务端'
            else:
                customer_lookup = self._lookup_customer(text, p, old['pending'])
                if customer_lookup is None:
                    output = self._interpret(cid, text, old['pending'], metadata, on_text)
                else:
                    output = customer_lookup
                    metadata['source'] = '服务端'
                pending = output['pending']
                requested = output['intent']
                if requested == 'chat':
                    metadata['mode'] = 'chat'
                else:
                    if pending and customer_lookup is None:
                        requested = json.loads(pending).get('intent', requested)
                    if requested in ACTION_PERMISSIONS:
                        require_permission(p, ACTION_PERMISSIONS[requested])
                if output['call_api'] and output['intent']=='nl_query':
                    query=json.loads(output['http_body'])
                    require_permission(p,INTENT_PERMISSIONS[query['intent']])
                metadata.update(action=requested,method=output['method'].upper() if output['call_api'] else None)
                reply=output['reply']
                if output['call_api']:
                    status,result=self.executor(output['method'],output['http_url'],output['http_body'],employee_token)
                    metadata.update(executed=True,http_status=status,action=output['intent'])
                    if 200 <= status < 300 and output['intent'] in ('tickets', 'ticket_detail', 'ticket_update'):
                        response = json.loads(result)
                        rows = response.get('data')
                        rows = rows if isinstance(rows, list) else [rows] if isinstance(rows, dict) else []
                        metadata['feedback_ticket_ids'] = [row['id'] for row in rows if isinstance(row, dict) and type(row.get('id')) is int]
                    reply=business_reply(status,result,output['intent'])
                    if status==200 and output['intent']=='managed_daily_list':
                        rows=json.loads(result)['data']['items'][:10]
                        if rows:
                            metadata['report_employee_ids']=sorted({row['employee_id'] for row in rows})
                    if pending and output['intent'] in ('lead_list','leave_candidates'):
                        candidate_state=json.loads(pending)
                        if candidate_state.get('state')=='id':
                            reply,pending=self._candidate_reply(status,result,candidate_state,reply)
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

    def _lookup_customer(self, text, principal, pending):
        match = _CUSTOMER_NAME_LOOKUP.fullmatch(text)
        if match is None:
            return None
        name = match['name']
        explicit = bool(match['customer'])
        if name.startswith(_NON_CUSTOMER_NAMES) or name.endswith(_NON_CUSTOMER_NAMES):
            return None
        if not explicit and (len(name) > 4 or name.startswith(_NON_CUSTOMER_PREFIXES)):
            return None
        if not explicit and 'crm:read' not in principal.permissions:
            return None
        require_permission(principal, 'crm:read')
        try:
            lead = ConsultantRepository(self.db).find_lead_by_name(name, principal.employee_id)
        except ConflictError:
            reply = f'当前名下有多位名为“{name}”的客户，请按客户编号查询。'
        else:
            if lead is not None:
                action = json.dumps({'intent': 'lead_detail', 'params': {'lead_id': lead.id}})
                return {**plan(action, text), 'pending': pending or ''}
            if not explicit:
                return None
            reply = f'当前名下没有查到姓名为“{name}”的客户，请核对姓名或客户编号。'
        return {'intent': 'lead_detail', 'call_api': False, 'pending': pending or '', 'reply': reply}

    def _interpret(self, cid, text, pending, metadata, on_text=None):
        saved = json.loads(pending) if pending else {}
        if text.rstrip('。！! ') in CONFIRM | CANCEL or (saved.get('state') == 'id' and selected_id(text) is not None):
            metadata['source'] = '服务端确认状态机'
            return plan('', text, pending)

        history = chat_history(self.repo.history(cid, limit=12))
        model_text = self.extractor.extract(text, pending, history, **({"on_text": on_text} if on_text else {}))
        try:
            action = parse_action(model_text)
        except (ValueError, TypeError):
            return plan(model_text, text, pending)

        intent = action.get('intent')
        if intent == 'chat':
            answer = action.get('reply')
            if action['params'] or not isinstance(answer, str) or not answer.strip():
                answer = '刚才没能生成回复，请再试一次。'
            return {'intent': 'chat', 'call_api': False, 'pending': pending or '', 'reply': answer.strip()[:1600]}
        if intent == 'daily_submit':
            for key in ('key_progress', 'risks'):
                value = action['params'].get(key)
                if isinstance(value, str):
                    action['params'][key] = [line.strip() for line in value.splitlines() if line.strip()]
            model_text = json.dumps(action, ensure_ascii=False)
        return plan(model_text, text, pending)

    @staticmethod
    def _candidate_reply(status, body, pending, fallback):
        if status != 200:
            return fallback, ''
        data=json.loads(body)
        if data.get('code')!=0 or not isinstance(data.get('data'),dict):
            return fallback, ''
        result=data['data']
        rows=result.get('items',[])
        leave=pending.get('field')=='leave_id'
        if not rows:
            return ('没有找到你负责审批的待处理请假单。' if leave else '没有找到你有权查看的匹配客户。'), ''
        pending['choices']=[row['id'] for row in rows]
        if leave:
            candidates=[f"请假单 {row['id']} · {row['student_name']}（学生编号 {row['student_id']}）· "
                        f"{row['start_time']} 至 {row['end_time']}" for row in rows]
        else:
            candidates=[f"客户 {row['id']} · {row['customer_name']} · {row.get('intended_country') or '未填意向国家'}"
                        for row in rows]
        reply='请回复“选择”加编号。\n'+'\n'.join(candidates)
        if result.get('has_more') or result.get('total',0)>len(rows):
            reply+='\n这里只显示部分结果。知道编号时也可重新发起带编号的请求。'
        return reply,json.dumps(pending,ensure_ascii=False)
