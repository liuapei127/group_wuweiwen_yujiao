# 客户管理 · 第一条 Dify 闭环（实施说明）

> 采纳 GPT 修订：**不按 HTTP 节点个数验收**，按「录入 → 查库可核对 → 状态更新 → 再查一致」验收。  
> **暂不操作云端**；本地通过后交集成负责人 `docker compose ... --build --no-deps api`。

---

## 1. 闭环定义

| 步骤 | 验收标准 |
| --- | --- |
| 1 录入 | Dify 自然语言 → API → **`crm_lead` 有新行** |
| 2 查询 | 返回 **数据库真实字段**，非模型编造 |
| 3 跟进 | `crm_follow_up` 有记录，`last_contact_time` 更新 |
| 4 状态 | 合法状态机；流失带 `lost_reason` |
| 5 复查 | 同客户再查，状态与跟进一致 |

---

## 2. Chatflow 逻辑（Dify 1.16）

### 2.1 意图路由（LLM 或分类器）

| 意图 | 说明 |
| --- | --- |
| `lead_create` | 录入新客户 |
| `lead_query` | 查列表/查某人 |
| `lead_detail` | 档案+跟进 |
| `lead_status` | 改状态 |
| `lead_follow_up` | 写跟进 |
| `other` | 兜底说明能力边界 |

### 2.2 节点序列（示意）

```
开始 → 意图识别(LLM)
  ├─ lead_create → 参数提取(LLM, JSON Schema) → 缺参? → 追问 → 合并
  │                    ↓
  │              HTTP POST /api/v1/consultant/leads
  │                    ↓
  │              判断 code==0 ? → 直接回复 / 错误分支
  ├─ lead_query → (可选) HTTP GET /api/v1/consultant/leads?keyword=
  ├─ lead_detail → 若仅有姓名且无 id → HTTP NL2SQL 或 GET list 消歧（**待加强**）
  │              → HTTP GET /api/v1/consultant/leads/{lead_id}
  ├─ lead_status → 提取 lead_id 或 customer_name + status
  │              → HTTP PATCH .../status 或 POST /api/v1/enterprise/commands
  └─ lead_follow_up → HTTP POST .../follow-ups
```

### 2.3 身份传递（当前临时 / 目标）

| 阶段 | 做法 |
| --- | --- |
| **现** | HTTP 头 `X-Employee-Id: {{employee_id}}`（变量来自登录前可写死测试 `1`） |
| **目标** | 与 auth 模块：Dify 带 **服务端 Token**，FastAPI 验签后得 `employee_id` |

**安全**：`code≠0` 或 HTTP ≥400 时，回复节点只允许报错话术，**禁止**「已录入/已更新」。

### 2.4 参数提取 Prompt 职责（示例）

```
你是企业 CRM 助手。从员工输入提取 JSON：
customer_name, contact_info, intended_country, intended_major, source_channel, owner_employee_id。
缺失必填 customer_name 或 owner_employee_id 时输出 {"need_clarify": true, "question": "..."}。
不要编造未出现的电话号码。
```

### 2.5 HTTP 节点配置（本地 Dify 调 Windows 后端）

| 环境 | Base URL |
| --- | --- |
| 云端 Dify → 云端 API | `http://education-api:8000` |
| 本机 Dify Docker → 本机 API | `http://host.docker.internal:8000`（需 `0.0.0.0:8000` 监听） |

**示例：录入**

- Method: `POST`
- URL: `{{base}}/api/v1/consultant/leads`
- Body: LLM 输出 JSON
- Headers: `Content-Type: application/json`, `X-Employee-Id: {{employee_id}}`

**示例：NL2SQL 查跟进**

- `POST {{base}}/api/v1/ai/nl2sql/query`
- Body: `{"intent":"lead_follow_ups_by_name","params":{"customer_name":"{{name}}"}`

---

## 3. 错误分支（必做）

| 条件 | 对用户回复 |
| --- | --- |
| `code=404` | 未找到客户，请核对姓名或提供编号 |
| `code=403` | 无权操作该客户 |
| `code=400` 状态机 | 说明当前状态不允许该操作 |
| 超时/502 | 系统繁忙，请稍后；**不要**声称成功 |
| LLM 缺参 | 追问一句，不调用 API |

---

## 4. 测试步骤（四态填表）

1. 本地：`education_service` + `aiproject/.env` + `uvicorn app.main:app --host 0.0.0.0 --port 8000`
2. Swagger 或 curl 单测各 API → 符合性表「已测试」列打勾
3. Dify 跑通录入一句 → MySQL `SELECT * FROM crm_lead ORDER BY id DESC LIMIT 1`
4. 同会话查详情、写跟进、改 `contacting` → 再查
5. 集成 build 后，Dify 用 `education-api` 重复 3～4 → 「已部署」「已验收」

**测试台词建议**

- 「帮我把客户王明记下来，手机 139xxxx，想去新加坡，负责人是我。」
- 「查一下王明的跟进记录。」
- 「王明标记为意向跟进中。」

---

## 5. 与 GPT 评审对齐的「未完成声明」

- **口述日报**：本闭环不包含；语音转写未做。  
- **成绩/投诉/组织/新人/主动待办**：不在第一条闭环范围。  
- **请假**：需木合塔尔 STU-01 后另开闭环文档。  
- **认证**：当前闭环仅适合 **联调/答辩彩排**，生产须接 auth。

---

## 6. 提交集成负责人前检查单

- [ ] 符合性表四态已更新  
- [ ] API 文档与 `router_registry.py` 一致  
- [ ] 未改共享表结构、未跑 DROP 脚本  
- [ ] `pyproject.toml` 依赖变更已说明  
- [ ] 仅 ENT 目录改动，未覆盖他人模块  
