# ENT 企业助手 · Dify Chatflow 搭建清单（可直接照抄）

> **控制台**：`http://127.0.0.1:8088/apps`（本地端口若改过以 `.env` 为准）  
> **ENT API**：先执行 `aiproject\scripts\start_api_for_dify.ps1`，探活 `http://127.0.0.1:8000/health`  
> **Dify 容器调 API**：`http://host.docker.internal:8000`（不要用容器内的 127.0.0.1）

---

## 0. 创建应用

1. **创建空白应用** → 类型选 **「Chatflow」**（高级对话 / 工作流编排）  
2. 名称：`企业智能助手-ENT`（或组内统一命名）  
3. **环境变量**（应用设置 → 变量）  

| 变量名 | 值 | 说明 |
| --- | --- | --- |
| `base_url` | `http://host.docker.internal:8000` | Docker 访问宿主机 API |
| `employee_id` | `1` | **临时**；等 JWT 后删除，改 Authorization |

4. **对话变量**（可选）：`last_lead_id` 用于多轮追问

---

## 1. 全局：先探活（必做）

**HTTP 请求** 节点 `health_check`：

- Method: `GET`  
- URL: `{{#env.base_url#}}/health`  
- 超时: 15s  

**条件分支**（或代码节点解析）：

- 若 HTTP 200 且 body 含 `"status":"ok"` → 继续  
- 若失败 → **直接回复**：「后端未启动，请先运行 start_api_for_dify.ps1」

---

## 2. 意图识别（LLM）

**模型**：任选已配置的 LLM（如 deepseek / openai 兼容）

**系统 Prompt（复制）**：

```text
你是企业内部 CRM 助手。根据员工一句话，只输出一个 JSON（不要 markdown）：
{"intent":"lead_create"|"lead_query"|"lead_detail"|"lead_status"|"lead_follow_up"|"other","reason":"..."}

规则：
- 录入新客户 → lead_create
- 搜客户列表 → lead_query
- 看某客户档案/跟进 → lead_detail
- 改状态/签约/流失 → lead_status
- 写跟进记录 → lead_follow_up
- 其他 → other
```

**用户输入**：`{{#sys.query#}}`

---

## 3. 分支：录入客户 `lead_create`

### 3.1 参数提取 LLM

```text
从员工输入提取 JSON。必填 customer_name。
可选：contact_info, intended_country, intended_major, source_channel。
若缺 customer_name：{"need_clarify":true,"question":"请提供客户姓名"}。
不要编造电话。
```

### 3.2 HTTP POST 录入

- URL: `{{#env.base_url#}}/api/v1/consultant/leads`  
- Method: `POST`  
- Headers:  
  - `Content-Type: application/json`  
  - `Authorization: Bearer {{#env.employee_id#}}`（若 main 仍 503，**仅测试**可用 header 覆盖，见下）  
- Body: 上一步 LLM 的 JSON（映射字段）

**503 分支（当前正式 main）**  
若 status=503 → 回复：「员工身份未就绪（公共 JWT 未接入），接口已保护。」

**成功分支**  
`code==0` → 回复「已录入，lead_id=…」并展示 API 返回字段；**禁止**编造未返回的字段。

---

## 4. 分支：查列表 `lead_query`

- `GET {{#env.base_url#}}/api/v1/consultant/leads?keyword={{keyword}}`  
- keyword 由 LLM 从用户话里抽  
- 503 / 403 / 非 0 code → 对应错误话术（见《客户管理-Dify闭环说明》§3）

---

## 5. 分支：详情 `lead_detail`

1. 若有 `lead_id` → `GET .../leads/{lead_id}`  
2. 若只有姓名 → `GET .../leads?keyword=姓名`，多条则追问选 ID（不要擅自选第一条）  
3. 需要跟进历史时 → `POST .../ai/nl2sql/query` body:

```json
{
  "intent": "lead_follow_ups_by_name",
  "params": { "customer_name": "{{name}}" }
}
```

---

## 6. 分支：改状态 `lead_status`

- `PATCH {{#env.base_url#}}/api/v1/consultant/leads/{{lead_id}}/status`  
- Body: `{"status":"...", "lost_reason":"..."}`（流失必填原因）  
- 或命令式：`POST .../enterprise/commands`  
  `{"action":"update_lead_status_by_name","params":{"customer_name":"...","status":"..."}}`

---

## 7. 分支：写跟进 `lead_follow_up`

- `POST {{#env.base_url#}}/api/v1/consultant/leads/{{lead_id}}/follow-ups`  
- Body: `{"content":"...", "follow_type":"phone"}` 等（以 OpenAPI 为准）

---

## 8. 从 OpenAPI 导入（推荐，少手填）

1. API 已启动时，Dify → **工具** → **自定义** → **从 URL 导入**  
2. URL: `http://host.docker.internal:8000/openapi.json`  
3. 在 Chatflow 里用 **工具节点** 绑定 `consultant` 相关 operation（路径以 Swagger 为准）

---

## 9. 验收四态（本地）

按 `客户管理-Dify闭环说明.md`：录入 → 查库 → 跟进 → 改状态 → 再查一致。  
**main 上 503 时**：先用 `tests.repro` 或等 JWT 后再验收正式入口。

---

## 10. 与 Cursor / Chrome 自动化

- Chrome DevTools 远程调试 `127.0.0.1:9222` 可由 `user-chrome-devtools` 操控已登录的控制台。  
- **Dify MCP**（`user-dify`）写入工作流需 **控制台 Cookie**：登录后执行 `auth_import_cookies` 或配置 `DIFY_CONSOLE_COOKIE`，方可 `workflow_sync_draft` 程序化改图。

## 11. 本机已创建应用（Cursor 操控 Chrome 2026-11-12）

| 项 | 值 |
| --- | --- |
| 名称 | **企业智能助手-ENT** |
| 类型 | Chatflow |
| 应用 ID | `ac18cfb8-3f60-406f-99dd-d9cc635dc71f` |
| 编排 URL | http://127.0.0.1:8088/app/ac18cfb8-3f60-406f-99dd-d9cc635dc71f/workflow |
| 状态 | **已发布 v1（10 节点全链）**；v2 修复在 `ent-workflow-graph.json`，明早同步见 `docs/回复Cursor/50-ENT-Dify全量测试报告.md` §6 |

*文档版本：2026-11-12*
