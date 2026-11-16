"""Refresh the portal Chatflow prompts and validation without replacing its 32-node graph."""
import json
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DSL = ROOT / "docs/dify"
path = DSL / "local-integration/ent.yml"
package = yaml.safe_load(path.read_text(encoding="utf-8"))
workflow = package["workflow"]
nodes = {node["id"]: node["data"] for node in workflow["graph"]["nodes"]}
portal = json.loads((DSL / "ent-portal-intent-workflow.yml").read_text(encoding="utf-8"))["workflow"]
portal_nodes = {node["id"]: node["data"] for node in portal["graph"]["nodes"]}
nodes["start"]["variables"] = [var for var in portal_nodes["start"]["variables"] if var["variable"] != "query"]
nodes["llm"]["title"] = portal_nodes["llm"]["title"]
nodes["llm"]["prompt_template"] = [
    {**prompt, "text": prompt["text"].replace("{{#start.query#}}", "{{#sys.query#}}")}
    for prompt in portal_nodes["llm"]["prompt_template"]
]
contract = (ROOT / "app/ai/workflows/ent_contracts.py").read_text(encoding="utf-8")
nodes["plan"]["code"] = contract + "\n\ndef main(text: str, query: str, pending: str) -> dict:\n    return plan(text, query, pending)\n"
workflow["features"]["opening_statement"] = "可以和我聊聊，也可以查询你有权访问的客户、请假和日报。提交或修改资料前，我会先请你确认。"
workflow["features"]["suggested_questions"] = [
    "查看我的待办", "查看本周所管组织的日报", "查询王明有多少条跟进", "查询张三的待审批请假",
]
assert len(nodes) == 32
assert [node["url"] for node in nodes.values() if node["type"] == "http-request"] == [
    "http://host.docker.internal:8003/health"
]
path.write_text(yaml.safe_dump(package, allow_unicode=True, sort_keys=False), encoding="utf-8")
