"""Pure contracts shared by Dify sandbox nodes and local regression tests."""
import json
import re
from urllib.parse import urlencode

ACTIONS = {
 'lead_create': ('post','/api/v1/consultant/leads','customer_name','customer_name contact_info gender age education_level intended_country intended_major background_info source_channel remark'),
 'lead_list': ('get','/api/v1/consultant/leads','','keyword status page page_size'),
 'lead_detail': ('get','/api/v1/consultant/leads/{lead_id}','lead_id','lead_id customer_name'),
 'lead_update': ('patch','/api/v1/consultant/leads/{lead_id}','lead_id','lead_id customer_name contact_info intended_country intended_major background_info remark'),
 'lead_status': ('patch','/api/v1/consultant/leads/{lead_id}/status','lead_id status','lead_id customer_name status lost_reason'),
 'lead_follow_up': ('post','/api/v1/consultant/leads/{lead_id}/follow-ups','lead_id content','lead_id customer_name content follow_type next_plan'),
 'daily_submit': ('post','/api/v1/employee-reports','content','content report_date raw_content key_progress risks next_plan'),
 'daily_list': ('get','/api/v1/employee-reports','','date_from date_to'),
 'organizations': ('get','/api/v1/enterprise/organizations','','keyword limit'),
 'colleagues': ('get','/api/v1/enterprise/organizations/colleagues','name','name'),
 'colleague_contact': ('get','/api/v1/enterprise/colleagues/{employee_id}/contact','employee_id','employee_id'),
 'guides': ('get','/api/v1/enterprise/onboarding-guides','','keyword category page page_size'),
 'guide_create': ('post','/api/v1/enterprise/onboarding-guides','title category content','title category content'),
 'score_create': ('post','/api/v1/enterprise/scores','student_id course_name score','student_id course_name score semester credit exam_key submission_key'),
 'scores': ('get','/api/v1/enterprise/scores','student_id','student_id semester limit'),
 'score_correct': ('put','/api/v1/enterprise/scores/{score_id}','score_id student_id course_name score expected_version','score_id student_id course_name score semester credit expected_version correction_reason'),
 'score_history': ('get','/api/v1/enterprise/scores/{score_id}/history','score_id','score_id limit'),
 'leaves': ('get','/api/v1/student-admin/leaves/pending','',''),
 'leave_approve': ('post','/api/v1/student-admin/leaves/{leave_id}/approve','leave_id decision','leave_id decision approval_comment'),
 'tickets': ('get','/api/v1/enterprise/tickets','','status limit'),
 'ticket_detail': ('get','/api/v1/enterprise/tickets/{ticket_id}','ticket_id','ticket_id'),
 'ticket_update': ('patch','/api/v1/enterprise/tickets/{ticket_id}','ticket_id expected_status status','ticket_id expected_status status solution'),
 'todos': ('get','/api/v1/enterprise/todos','','due_only limit'),
 'todo_create': ('post','/api/v1/enterprise/todos','title','title description due_time priority'),
 'todo_update': ('patch','/api/v1/enterprise/todos/{todo_id}','todo_id expected_status status','todo_id expected_status status'),
 'notifications': ('get','/api/v1/enterprise/notifications','','limit'),
 'nl_query': ('post','/api/v1/ai/nl2sql/query','intent params','intent params'),
}
READ_POST = {'nl_query'}
CONFIRM = {'确认','确认提交','确认执行','确认保存'}
CANCEL = {'取消','取消操作','不执行','不要执行','算了'}


def parse_action(text):
    value = re.sub(r'<think>.*?</think>', '', text or '', flags=re.DOTALL).strip()
    if value.startswith(chr(96)*3):
        value = re.sub(r'^\x60{3}(?:json)?\s*|\s*\x60{3}$', '', value)
    if value.startswith('ENT_ACTION:'):
        value = value.split(':',1)[1].strip()
    obj = json.loads(value)
    if not isinstance(obj,dict):raise ValueError('not an object')
    if 'params' not in obj:
        obj = {'intent':obj.get('intent'),'params':{k:v for k,v in obj.items() if k!='intent'}}
    if not isinstance(obj.get('params'),dict):raise ValueError('params not an object')
    return obj


def plan(text, query, pending=''):
    out={'call_api':False,'method':'get','http_url':'','http_body':'','reply':'未识别到可执行的操作，没有修改数据。','pending':'','intent':'other'}
    try:old=json.loads(pending) if pending else {}
    except ValueError:old={}
    normalized=re.sub(r'[。！!\s]+$','',(query or '').strip())
    if normalized in CANCEL:
        out['reply']='已取消待确认操作，没有提交请求。';return out
    if normalized in CONFIRM:
        if old.get('state')!='confirm':
            out['reply']='没有待确认的操作，请先说明要处理的数据。';return out
        action=old;confirmed=True
    elif old.get('state')=='id' and re.fullmatch(r'(?:选择|编号)?\s*\d+',normalized):
        action={'intent':old['intent'],'params':dict(old['params'])}
        action['params']['lead_id']=int(re.search(r'\d+',normalized).group());confirmed=False
    else:
        try:action=parse_action(text)
        except (ValueError,TypeError):
            out['reply']='请补充具体操作和必要字段；未执行任何写入。';out['pending']=pending;return out
        confirmed=False
    intent=action.get('intent')
    if intent not in ACTIONS:
        out['reply']='这是功能咨询或暂不支持的操作，没有调用业务接口。可查询客户、日报、组织、指南、成绩、请假、工单、待办及通知；写操作需要确认。';return out
    method,template,required,allowed=ACTIONS[intent]
    params={k:v for k,v in action.get('params',{}).items() if v is not None}
    if set(params)-set(allowed.split()):
        out['reply']='包含不支持的字段或身份参数；员工身份只能由后端可信认证提供。未执行。';return out
    if not confirmed and method!='get' and intent not in READ_POST and re.search(r'不要|别执行|先不|暂不|是否支持|能否|如何|怎么|只是咨询',query or ''):
        out['reply']='按你的要求仅作说明，没有执行或排队写入。';return out
    if intent.startswith('lead_') and intent not in ('lead_create','lead_list') and not params.get('lead_id') and params.get('customer_name'):
        target=dict(params);name=target.pop('customer_name')
        out['pending']=json.dumps({'intent':intent,'params':target,'state':'id'},ensure_ascii=False)
        return dict(out,call_api=True,intent='lead_list',http_url='http://host.docker.internal:8000/api/v1/consultant/leads?'+urlencode({'keyword':name,'page_size':10}),reply='先列出候选，请选择客户编号；不会自动选第一条。')
    params.pop('customer_name',None) if intent not in ('lead_create','lead_list') else None
    if intent=='lead_create':
        name=params.get('customer_name','')
        if not isinstance(name,str) or not name.strip() or name in ('未解析姓名','未知','待补充'):
            params.pop('customer_name',None)
        elif not confirmed and name not in (query or ''):
            params.pop('customer_name',None)
    missing=[k for k in required.split() if k not in params or params[k]=='']
    if missing:
        out['reply']='请补充：'+', '.join(missing)+'。未调用接口。'
        out['pending']=json.dumps({'intent':intent,'params':params,'state':'collect'},ensure_ascii=False);return out
    for k in list(params):
        if k.endswith('_id') or k in ('expected_version','page','page_size','limit'):
            if isinstance(params[k],bool) or not re.fullmatch(r'[1-9]\d*',str(params[k])):
                out['reply']='编号、版本和分页参数必须为正整数。未执行。';return out
            params[k]=int(params[k])
    if intent=='nl_query':
        if params['intent'] not in ('leads_by_status','lead_detail_by_name','lead_follow_ups_by_name','pending_leaves','daily_reports_recent') or not isinstance(params['params'],dict):
            out['reply']='仅允许白名单查询意图，不接受SQL。';return out
        if {'sql','employee_id','owner_employee_id','approver_id'} & set(params['params']):
            out['reply']='不能通过查询参数覆盖身份范围或提交SQL。';return out
    if method!='get' and intent not in READ_POST and not confirmed:
        out['reply']='请核对以下操作，回复“确认”才会提交；回复“取消”放弃。\n'+intent+'\n'+json.dumps(params,ensure_ascii=False)
        out['pending']=json.dumps({'intent':intent,'params':params,'state':'confirm'},ensure_ascii=False);return out
    path_fields={k:params[k] for k in re.findall(r'\{(\w+)\}',template)}
    payload={k:v for k,v in params.items() if k not in path_fields}
    out.update(call_api=True,intent=intent,method=method,http_url='http://host.docker.internal:8000'+template.format(**path_fields))
    if method=='get':
        if payload:out['http_url']+='?'+urlencode(payload)
    else:out['http_body']=json.dumps(payload,ensure_ascii=False)
    out['reply']='请求处理中，结果以实际后端响应为准。';return out


def format_result(status_code, body, intent):
    try:data=json.loads(body or '{}')
    except (ValueError,TypeError):data={}
    status=int(status_code or 0)
    if status==503:return {'reply':'员工可信身份或后端服务未就绪（HTTP 503），没有确认保存成功。请等待管理员接入身份后重试。'}
    if status==403:return {'reply':'无权操作或数据不在授权范围（HTTP 403），未确认任何修改。'}
    if status==409:return {'reply':'数据状态或版本冲突（HTTP 409），请重新查询并选择编号/最新版本，不自动重试。'}
    if status==422:return {'reply':'字段校验未通过（HTTP 422），请核对必填字段、编号和格式。'}
    if status==404:return {'reply':'未找到记录（HTTP 404），请核对编号。'}
    if status<200 or status>=300:return {'reply':'请求失败或网络异常，未确认操作成功；如涉及写入请先查询核对，不自动重试。'}
    if not isinstance(data,dict) or data.get('code')!=0:return {'reply':'后端返回业务失败或非预期格式，未确认操作成功。请查询核对。'}
    result=data.get('data')
    if ACTIONS[intent][0]!='get' and intent not in READ_POST:
        rid=result.get('id') if isinstance(result,dict) else None
        if not isinstance(rid,int) or isinstance(rid,bool) or rid<1:
            return {'reply':'后端响应缺少可核对的记录编号，未确认操作成功，请查询核对。'}
        return {'reply':'后端已确认操作成功。结果：'+json.dumps(result,ensure_ascii=False)}
    return {'reply':'后端查询结果（仅来自实际响应）：\n'+json.dumps(result,ensure_ascii=False)}


def failure_reply(error_message, error_type):
    match=re.search(r'(?:status(?:\s+code)?)[^0-9]*(\d{3})',error_message or '',re.I)
    if match:return format_result(int(match.group(1)),'{}','lead_list')
    return {'reply':'请求未完成（网络或节点错误），没有确认保存成功。请先查询核对；不会自动重试写入。'}
