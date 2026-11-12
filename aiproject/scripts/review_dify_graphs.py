"""Read-only parser review; keep historical audit evidence unchanged."""
import argparse,ast,hashlib,json
from pathlib import Path
from urllib.parse import urlsplit,parse_qs
ROOT=Path(__file__).resolve().parents[1]
CASES=[
 ('P01','标准标记','ENT_ACTION:{"intent":"lead_create","customer_name":"验证甲"}','录入客户验证甲','lead_create'),
 ('P02','标记后空格','ENT_ACTION: {"intent":"lead_create","customer_name":"验证甲"}','录入客户验证甲','lead_create'),
 ('P03','多行JSON','ENT_ACTION:\n{\n"intent":"lead_create",\n"customer_name":"验证甲"\n}','录入客户验证甲','lead_create'),
 ('P04','缺少姓名必须追问','请提供客户姓名。','录入客户','other'),
 ('P05','咨询且明确不执行','支持录入客户，请先提供资料。','这个功能是否支持录入客户？先不要执行。','other'),
 ('P06','不完整成绩不得执行','ENT_ACTION:{"intent":"score_create","student_id":101,"score":80}','录入成绩','other'),
 ('P07','缺姓名不得执行','ENT_ACTION:{"intent":"lead_create"}','新增线索','other'),
 ('P08','紧凑姓名查询','正在查询客户验证甲。','查询客户验证甲','clarify_or_exact'),
]

def review(name,graph):
 nodes={n['id']:n['data'] for n in graph['nodes']};modern='plan' in nodes
 code=nodes['plan' if modern else 'code1']['code'];scope={}
 imports={ast.unparse(n) for n in ast.parse(code).body if isinstance(n,(ast.Import,ast.ImportFrom))}
 if imports-{'import json, re','import json','import re','from urllib.parse import quote','from urllib.parse import urlencode'}:raise RuntimeError('Unexpected parser imports')
 exec(compile(code,name,'exec'),scope)
 condition=nodes['execute' if modern else 'if1']['cases'][0]['conditions'][0]
 results=[]
 for cid,label,text,query,expected in CASES:
  output=scope['main'](text,query,'') if modern else scope['main'](text,query)
  pending=json.loads(output.get('pending') or '{}')
  route=output['call_api'] if modern else (output['intent']!='other' if condition['variable_selector'][-1]=='intent' else not output['skip'])
  actual=(pending.get('intent','other') if pending.get('state')=='confirm' else output['intent'] if route else 'other')
  passed=(not route or parse_qs(urlsplit(output['http_url']).query).get('keyword')==['验证甲']) if expected=='clarify_or_exact' else actual==expected
  if modern and expected=='lead_create':passed=passed and not route and scope['main']('','确认',output['pending'])['call_api']
  results.append({'id':cid,'case':label,'expected':expected,'routed_or_pending_intent':actual,'will_call_http':route,'outputs':output,'passed':passed})
 return {'name':name,'nodes':len(nodes),'edges':len(graph['edges']),'graph_sha256':hashlib.sha256(json.dumps(graph,sort_keys=True,ensure_ascii=False).encode()).hexdigest(),'parser_cases':results,'http_nodes':[{'id':nid,'method':d.get('method'),'error_strategy':d.get('error_strategy','fail'),'retry_enabled':d.get('retry_config',{}).get('retry_enabled'),'url':d.get('url')} for nid,d in nodes.items() if d['type']=='http-request'],'supported_business_http_paths':sorted({v[1] for v in scope.get('ACTIONS',{}).values()}) if modern else ['/api/v1/consultant/leads'],'conversation_confirmation_state_nodes':[nid for nid,d in nodes.items() if d['type'] in ('assigner','human-input','variable-assigner')]}

def main():
 p=argparse.ArgumentParser();p.add_argument('--output',default='docs/回复Cursor/runs/dify-graph-repair-review-2026-11-12.json');args=p.parse_args()
 rows=json.loads((ROOT/'docs/回复Cursor/runs/dify-review-graphs-2026-11-12.json').read_text(encoding='utf-8'))
 variants=[(r['version'],r['graph']) for r in rows]+[('repository_v3',json.loads((ROOT/'docs/dify/ent-workflow-graph.json').read_text(encoding='utf-8')))]
 report={'variants':[review(n,g) for n,g in variants]}
 (ROOT/args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'variants':[{'name':v['name'],'passed':sum(r['passed'] for r in v['parser_cases']),'total':len(CASES),'failed':[r['id'] for r in v['parser_cases'] if not r['passed']]} for v in report['variants']]},ensure_ascii=False))
 if not all(c['passed'] for c in report['variants'][-1]['parser_cases']):raise SystemExit(1)

if __name__=='__main__':main()
