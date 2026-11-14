"""Build the private Dify intent-only workflow used by the authenticated portal."""
import json
from pathlib import Path
from app.ai.workflows.ent_contracts import ACTIONS
ROOT=Path(__file__).resolve().parents[1]
source=json.loads((ROOT/'docs/dify/ent-workflow-graph.json').read_text(encoding='utf-8'))
model=next(n['data']['model'] for n in source['nodes'] if n['data']['type']=='llm')
prompt='''你是ENT业务参数抽取器。只输出一个JSON对象：{"intent":"动作名","params":{}}。不输出解释、SQL、成功话术或Markdown。
只从用户明确输入和下方同一待处理状态抽取事实，不编造姓名、编号、联系方式、版本或考试标识。缺字段保持缺失。
禁止输出owner_employee_id、approver_id、recorded_by或操作者employee_id；colleague_contact中的employee_id仅是查询对象编号。
用户否定、只咨询或要求删除数据时intent=other。确认、取消由服务端处理，模型不得自行确认。
用户补字段时，仅合并同一待处理动作的已知字段。只有姓名没有lead_id时保留customer_name，不能猜编号。
客户状态仅new/contacting/qualified/signed/lost；跟进类型phone/wechat/meeting/email/other。
日报key_progress和risks是字符串数组，next_plan和content为字符串；report_date格式YYYY-MM-DD。
成绩score为十进制数字或数字字符串；更正必须有expected_version，未知版本先留空。
工单状态pending→processing→resolved→closed，更正状态不得臆造expected_status；解决/关闭需要solution。
待办状态pending/in_progress/done/cancelled；创建时不需expected_status，更新时必须有expected_status。
请假decision仅approved/rejected。“同意张三请假”用leave_approve，填写student_name和decision，缺请假单编号时交由后端列出该老师的候选。不能猜编号。只查某人的请假单用leave_candidates。示例：输入“同意张三的请假”，输出 {"intent":"leave_approve","params":{"student_name":"张三","decision":"approved"}}。
“王明有多少条跟进”用lead_followup_count，填写customer_name或用户明确提供的lead_id。“查看王明的跟进记录”用nl_query中的lead_follow_ups_by_name。
“查看下属/所管组织/团队的日报”用managed_daily_list；点名时employee_name仅填用户明确给出的员工姓名。“本周多少人次提交”用daily_submission_summary。日/周对应period为day/week。
“生成正式日报/周报”使用formal_report，分别传report_kind为daily/weekly。仅抽取指令并等待服务端确认。anchor只填明确的YYYY-MM-DD日期，或根据下方服务端日期换算今日、昨日、本周、上周。自然周从星期一开始，上周用前一周任一天。
白名单查询nl_query的params为{"intent":"白名单名","params":{}}，白名单仅：
leads_by_status(status)、lead_detail_by_name(customer_name)、lead_follow_ups_by_name(customer_name)、pending_leaves(空对象)、daily_reports_recent(空对象)。
不要把普通业务查询全部变成nl_query；只有查询跟进或用户明确指定时用此动作。客户列表用lead_list，近期本人日报用daily_list。
动作目录（method,path,required,allowed）：
'''+json.dumps(ACTIONS,ensure_ascii=False)+'\n服务端北京时间日期：{{#start.today#}}\n服务端待处理状态：{{#start.pending#}}'
nodes=[
 {'id':'start','type':'custom','position':{'x':0,'y':200},'data':{'type':'start','title':'门户输入','variables':[
  {'variable':'query','label':'query','type':'paragraph','required':True,'max_length':8000},
  {'variable':'pending','label':'pending','type':'paragraph','required':False,'max_length':32000},
  {'variable':'today','label':'today','type':'text-input','required':False,'max_length':10}]}},
 {'id':'llm','type':'custom','position':{'x':350,'y':200},'data':{'type':'llm','title':'只抽取业务动作和字段','model':model,
  'prompt_template':[{'id':'portal-system','role':'system','text':prompt},{'id':'portal-user','role':'user','text':'{{#start.query#}}'}],
  'context':{'enabled':False,'variable_selector':[]},'vision':{'enabled':False}}},
 {'id':'end','type':'custom','position':{'x':700,'y':200},'data':{'type':'end','title':'返回参数给可信后端','outputs':[{'variable':'text','value_selector':['llm','text'],'value_type':'string'}]}},
]
edges=[{'id':a+'-'+b,'source':a,'target':b,'sourceHandle':'source','targetHandle':'target','type':'custom',
 'data':{'sourceType':nodes[i]['data']['type'],'targetType':nodes[i+1]['data']['type'],'isInIteration':False,'isInLoop':False}}
 for i,(a,b) in enumerate([('start','llm'),('llm','end')])]
graph={'nodes':nodes,'edges':edges,'viewport':{'x':0,'y':0,'zoom':.8}}
package={'app':{'name':'ENT门户-参数理解','mode':'workflow','icon':'🤖','icon_background':'#DFF4EE','description':'私有服务端意图提取，业务权限、确认和执行在ENT后端。'},
 'kind':'app','version':'0.3.1','dependencies':[],'workflow':{'graph':graph,'features':{},'environment_variables':[],'conversation_variables':[]}}
(ROOT/'docs/dify/ent-portal-intent-workflow.yml').write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'nodes':len(nodes),'actions':len(ACTIONS),'file':'docs/dify/ent-portal-intent-workflow.yml'}))
