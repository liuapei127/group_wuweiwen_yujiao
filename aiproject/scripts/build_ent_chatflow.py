"""Build a reviewable Dify Chatflow from tested pure contracts; no API keys in DSL."""
import inspect,json,uuid
from pathlib import Path
from app.ai.workflows import ent_contracts as contract
ROOT=Path(__file__).resolve().parents[1]
original=json.loads((ROOT/'docs/dify/ent-workflow-graph.json').read_text(encoding='utf-8'))
model=next(n['data']['model'] for n in original['nodes'] if n['data']['type']=='llm')
nodes=[];edges=[]


def node(nid,kind,title,x,y,**data):
    nodes.append({'id':nid,'type':'custom','data':dict(type=kind,title=title,**data),'position':{'x':x,'y':y},'targetPosition':'left','sourcePosition':'right','width':244,'height':90})


def edge(source,target,handle='source'):
    types={n['id']:n['data']['type'] for n in nodes}
    edges.append({'id':source+'-'+handle+'-'+target,'source':source,'target':target,'sourceHandle':handle,'targetHandle':'target','type':'custom','data':{'sourceType':types[source],'targetType':types[target],'isInIteration':False,'isInLoop':False}})


def variable(name,selector,kind='string'):
    return {'variable':name,'value_selector':selector,'value_type':kind}


def code(nid,title,source,variables,outputs,x,y):
    node(nid,'code',title,x,y,code=source,code_language='python3',variables=variables,outputs={k:{'type':v,'children':None} for k,v in outputs.items()})


def condition(cid,selector,kind,value):
    return {'case_id':cid,'logical_operator':'and','conditions':[{'id':cid+'-condition','varType':kind,'variable_selector':selector,'comparison_operator':'is','value':value}]}


def http(nid,title,method,url,x,y,health=False):
    data=dict(method=method,url=url,variables=[],authorization={'type':'no-auth','config':None},headers='Content-Type: application/json' if method!='get' else '',params='',body={'type':'none','data':[]} if method=='get' else {'type':'json','data':[{'id':'body','type':'text','key':'','value':'{{#plan.http_body#}}'}]},ssl_verify=True,timeout={'max_connect_timeout':5,'max_read_timeout':10,'max_write_timeout':5},retry_config={'retry_enabled':False,'max_retries':0,'retry_interval':100})
    if health:
        data.update(error_strategy='default-value',default_value=[{'key':'status_code','type':'number','value':0},{'key':'body','type':'string','value':'{}'}])
    else:data['error_strategy']='fail-branch'
    node(nid,'http-request',title,x,y,**data)

node('start','start','用户输入',0,300,variables=[])
http('health','后端探活（短超时，不重试）','get','http://host.docker.internal:8000/health',300,300,health=True)
gate_source=inspect.cleandoc('''
import json,re

def main(query: str, status_code: int, body: str):
    try:healthy=int(status_code)==200 and json.loads(body).get('status')=='ok'
    except Exception:healthy=False
    if not healthy:return {'needs_llm':False,'reply':'后端探活未通过（网络或服务故障），没有执行业务操作。请检查API和SSRF代理。'}
    if re.search(r'健康检查|后端.*正常|探活|health',query,re.I):
        return {'needs_llm':False,'reply':'后端探活成功。员工可信身份尚未接入时，业务API仍会返回503；探活成功不代表业务已保存。'}
    if re.search(r'什么是.*503|503.*什么意思',query):
        return {'needs_llm':False,'reply':'HTTP 503表示服务暂不可用；本项目也用于员工可信身份未就绪。不能据此声称保存成功。'}
    return {'needs_llm':True,'reply':''}
''')
code('gate','核对实际健康响应',gate_source,[variable('query',['sys','query']),variable('status_code',['health','status_code'],'number'),variable('body',['health','body'])],{'needs_llm':'boolean','reply':'string'},600,300)
node('gate_if','if-else','是否需要理解业务输入',900,300,cases=[condition('true',['gate','needs_llm'],'boolean',True)])
node('health_answer','answer','探活或故障说明',1200,0,variables=[],answer='{{#gate.reply#}}')
prompt='你是ENT参数抽取器。只输出单个JSON对象：{"intent":"动作名","params":{...}}，不输出解释或成功话术。缺字段留空，不编造姓名、联系方式、ID、状态、版本或考试标识。不要输出员工身份参数。无法理解、功能咨询、删除数据或不支持的动作使用intent=other。用户说不要执行时不得构造写操作。\n动作目录（method/path/required/allowed）：\n'+json.dumps(contract.ACTIONS,ensure_ascii=False)+'\n待处理的会话状态：{{#conversation.pending_action#}}\n当用户补充字段时，合并同一待处理动作的已知字段。客户只有姓名而没有lead_id时，保留customer_name用于授权范围内候选查询，不能猜ID。成绩更正必须带expected_version；需要先查询最新成绩。正常员工日报只查本人，不提供主管越权能力。确认只由后续代码核对，模型不能自行确认。'
node('llm','llm','只抽取动作与字段',1200,300,model=model,prompt_template=[{'id':'ent-v3-system','role':'system','text':prompt}],context={'enabled':False,'variable_selector':[]},vision={'enabled':False},memory={'window':{'enabled':True,'size':10},'query_prompt_template':'{{#sys.query#}}','role_prefix':{'user':'','assistant':''}},error_strategy='fail-branch')
node('model_failure','answer','模型故障不执行',1500,700,variables=[],answer='模型暂不可用，未执行业务请求。请稍后重试。')
plan_source=Path(inspect.getfile(contract)).read_text(encoding='utf-8')+'\n\ndef main(text: str, query: str, pending: str):\n    return plan(text, query, pending)\n'
code('plan','验证动作、参数、确认与编号',plan_source,[variable('text',['llm','text']),variable('query',['sys','query']),variable('pending',['conversation','pending_action'])],{'call_api':'boolean','method':'string','http_url':'string','http_body':'string','reply':'string','pending':'string','intent':'string'},1500,300)
node('remember','assigner','保存或清除待确认动作',1800,300,version='2',items=[{'input_type':'variable','operation':'over-write','value':['plan','pending'],'variable_selector':['conversation','pending_action'],'write_mode':'over-write'}])
node('execute','if-else','只执行验证通过的请求',2100,300,cases=[condition('true',['plan','call_api'],'boolean',True)])
node('clarify','answer','追问、确认或取消',2400,0,variables=[],answer='{{#plan.reply#}}')
node('method','if-else','固定HTTP方法路由',2400,300,cases=[condition(m,['plan','method'],'string',m) for m in ('post','put','patch')])
format_source='import json,re\nACTIONS='+repr(contract.ACTIONS)+'\nREAD_POST='+repr(contract.READ_POST)+'\n'+inspect.getsource(contract.format_result)+'\n'+inspect.getsource(contract.failure_reply)
for index,method in enumerate(('get','post','put','patch')):
    y=300+index*450
    hid='http_'+method;fid='format_'+method;err='error_'+method
    http(hid,method.upper()+'调用业务API',method,'{{#plan.http_url#}}',2700,y)
    code(fid,'依据真实响应生成结果',format_source+'\ndef main(status_code: int, body: str, intent: str):\n    return format_result(status_code,body,intent)\n',[variable('status_code',[hid,'status_code'],'number'),variable('body',[hid,'body']),variable('intent',['plan','intent'])],{'reply':'string'},3000,y)
    code(err,'保留实际错误类型',format_source+'\ndef main(error_message: str, error_type: str):\n    return failure_reply(error_message,error_type)\n',[variable('error_message',[hid,'error_message']),variable('error_type',[hid,'error_type'])],{'reply':'string'},3000,y+180)
    node('answer_'+method,'answer','实际业务结果',3300,y,variables=[],answer='{{#'+fid+'.reply#}}')
    node('fail_'+method,'answer','失败不虚报成功',3300,y+180,variables=[],answer='{{#'+err+'.reply#}}')
    edge('method',hid,'false' if method=='get' else method)
    edge(hid,fid);edge(hid,err,'fail-branch');edge(fid,'answer_'+method);edge(err,'fail_'+method)
for source,target,handle in [('start','health','source'),('health','gate','source'),('gate','gate_if','source'),('gate_if','llm','true'),('gate_if','health_answer','false'),('llm','plan','source'),('llm','model_failure','fail-branch'),('plan','remember','source'),('remember','execute','source'),('execute','method','true'),('execute','clarify','false')]:edge(source,target,handle)
graph={'nodes':nodes,'edges':edges,'viewport':{'x':0,'y':0,'zoom':0.6}}
conversation=[{'id':'783f8620-5581-4cb7-9c62-f7d06b4946a0','name':'pending_action','selector':['conversation','pending_action'],'description':'服务端会话内的待确认动作，模型不得自行确认','value':'','value_type':'string'}]
features={'opening_statement':'你好，我是ENT企业助手。可处理已接入API的文字查询和操作；写入前会请求确认。员工身份未就绪时会说明503，不会假报成功。','suggested_questions':['后端健康检查','查询客户验证甲','查询学生1000004的成绩','查看我的待办'],'suggested_questions_after_answer':{'enabled':False},'text_to_speech':{'enabled':False},'speech_to_text':{'enabled':False},'retriever_resource':{'enabled':False},'sensitive_word_avoidance':{'enabled':False},'file_upload':{'enabled':False}}
package={'app':{'name':'企业智能助手-ENT','mode':'advanced-chat','icon':'🤖','icon_background':'#FFEAD5','description':'修复解析、确认、身份字段和错误处理；实际业务仍受可信身份保护。','use_icon_as_answer_icon':False},'dependencies':[],'kind':'app','version':'0.3.1','workflow':{'graph':graph,'features':features,'environment_variables':[],'conversation_variables':conversation}}
out=ROOT/'docs/dify'
(out/'ent-workflow-graph.json').write_text(json.dumps(graph,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'ent-workflow-v3-fixed.json').write_text(json.dumps(graph,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'ent-workflow-v3-fixed.yml').write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8')
(out/'ent-workflow-v3-conversation.json').write_text(json.dumps(conversation,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'nodes':len(nodes),'edges':len(edges),'actions':len(contract.ACTIONS),'file':'docs/dify/ent-workflow-v3-fixed.yml'},ensure_ascii=False))
