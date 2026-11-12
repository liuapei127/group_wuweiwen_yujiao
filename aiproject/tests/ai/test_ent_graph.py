"""Verify the shipped graph's safety boundaries and route catalogue against OpenAPI."""
import json
from pathlib import Path
from app.ai.workflows.ent_contracts import ACTIONS
from app.main import app
ROOT=Path(__file__).resolve().parents[2]


def test_shipped_graph_matches_tested_contract_and_registered_routes():
 graph=json.loads((ROOT/'docs/dify/ent-workflow-graph.json').read_text(encoding='utf-8'))
 package=json.loads((ROOT/'docs/dify/ent-workflow-v3-fixed.yml').read_text(encoding='utf-8'))
 assert graph==package['workflow']['graph']
 scope={};nodes={n['id']:n['data'] for n in graph['nodes']}
 exec(nodes['plan']['code'],scope)
 assert scope['ACTIONS']==ACTIONS
 for method,path,*_ in ACTIONS.values():assert method in app.openapi()['paths'][path]
 ids=set(nodes)
 assert all(e['source'] in ids and e['target'] in ids for e in graph['edges'])
 assert package['workflow']['conversation_variables'][0]['name']=='pending_action'
 for method in ('get','post','put','patch'):
  node=nodes['http_'+method]
  assert node['error_strategy']=='fail-branch'
  assert not node['retry_config']['retry_enabled']
  assert node['url']=='{{#plan.http_url#}}'
  assert any(e['source']=='http_'+method and e['sourceHandle']=='fail-branch' for e in graph['edges'])
 assert not package['workflow']['environment_variables']
