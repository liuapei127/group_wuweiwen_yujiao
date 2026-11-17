# 企业智能助手 · API 接口文档（真实路由版）

> 仅收录 **本仓库 `aiproject` 中已存在** 的路由。  
> **部署**：云端当前无下表 ENT 路径；Dify 生产基址为 `http://education-api:8000`（build 后生效）。  
> **本地**：`http://127.0.0.1:8000`。  
> 统一业务响应（ENT 模块）：`{"code":0,"message":"...","data":...}`；`code≠0` 为业务失败（HTTP 常为 200，以 body.code 为准）。

---

## 0. 系统（已上云）

### GET `/health`

| 项 | 说明 |
| --- | --- |
| 用途 | 进程存活 |
| 身份 | 无 |
| 成功示例 | `{"status":"ok"}` |
| 部署 | ✅ 云端已确认 |

### GET `/health/db`

| 项 | 说明 |
| --- | --- |
| 用途 | MySQL 连通（Dify 已用） |
| 成功示例 | `{"status":"ok","database":"connected"}` |
| 部署 | ✅ 云端已确认 |

---

## 1. 意向客户 `modules/consultant` — 前缀 `/api/v1/consultant`

### POST `/api/v1/consultant/leads` — 录入 ENT-01

| 项 | 说明 |
| --- | --- |
| 角色 | 销售顾问（**目标**：员工；**现**：无强鉴权） |
| 请求头 | `Content-Type: application/json`；可选 `X-Employee-Id`（未校验） |
| 表 | `crm_lead` INSERT |
| 状态流转 | 固定 `new` |

**请求示例**

```json
{
  "customer_name": "李明",
  "contact_info": "13700000002",
  "intended_country": "德国",
  "intended_major": "机械工程",
  "source_channel": "线下展会",
  "owner_employee_id": 1
}
```

**成功**：`code=0`，`data` 为 `LeadOut`。  
**失败**：校验失败由 FastAPI 422；业务错误 `code≠0`。

**权限/重复**：未实现手机号去重；`owner_employee_id` 由调用方传入。  
**测试/部署**：代码 ✅｜MySQL 联调 ❌｜云端 ❌

---

### GET `/api/v1/consultant/leads` — 分页查询 ENT-02

| 查询参数 | `keyword`, `status`, `owner_employee_id`, `page`, `page_size` |
| 表 | `crm_lead` SELECT |
| 数据权限 | ⏳ `owner_employee_id` 可选过滤；无经理全量策略 |

---

### GET `/api/v1/consultant/leads/{lead_id}` — 详情 + 跟进

| 表 | `crm_lead`, `crm_follow_up` |
| 失败 | 不存在 → `code=404` message |

---

### PATCH `/api/v1/consultant/leads/{lead_id}` — 更新档案字段

可更新：`contact_info`, `intended_*`, `background_info`, `remark`（见 `LeadUpdate`）。

---

### PATCH `/api/v1/consultant/leads/{lead_id}/status` — ENT-03

**请求示例**

```json
{
  "status": "signed"
}
```

流失时：

```json
{
  "status": "lost",
  "lost_reason": "预算不足"
}
```

**状态机**（`consultant/service.py`）  
`new→contacting|lost`；`contacting→qualified|signed|lost`；`qualified→signed|lost`；`lost→contacting`；`signed` 为终态。

**权限**：若带 `X-Employee-Id` 且与 `owner_employee_id` 不一致 → `code=403`。  
**重复**：终态不可再变。

---

### POST `/api/v1/consultant/leads/{lead_id}/follow-ups`

```json
{
  "employee_id": 1,
  "follow_type": "wechat",
  "content": "已加微信，发德国方案",
  "next_plan": "周三电话回访"
}
```

更新 `crm_lead.last_contact_time`。

---

## 2. 员工日报 `modules/employee_report` — 前缀 `/api/v1/employee-reports`

### POST `` — 提交 ENT-04

Dify 须在调用前完成结构化（**非语音完成标志**）。

```json
{
  "employee_id": 1,
  "content": "今日完成总结",
  "key_progress": ["跟进客户3人", "签约1人"],
  "risks": ["德国政策资料待更新"],
  "next_plan": "周五集中回访"
}
```

表：`employee_daily_report`；同日同员工 UPSERT（`uk_employee_date`）。

### GET `` — 查阅 ENT-05

查询：`employee_id`, `date_from`, `date_to`。  
**缺口**：无 `department` 筛选。

---

## 3. 学生行政（企业侧）`modules/student_admin` — 前缀 `/api/v1/student-admin`

### GET `/api/v1/student-admin/leaves/pending`

表：`student_admin_service`，`service_type=leave`，`status=pending`。

### POST `/api/v1/student-admin/leaves/{leave_id}/approve`

```json
{
  "approver_id": 1,
  "decision": "approved",
  "approval_comment": "同意病假"
}
```

**状态**：仅 `pending` 可批；否则 `code=400`。  
**重复审批**：已批记录再次调用应失败。  
**跨模块**：依赖 STU 写入 `pending`；**无**自动通知学生。

---

## 4. NL2SQL `ai/nl2sql` — 前缀 `/api/v1/ai/nl2sql`

### POST `/api/v1/ai/nl2sql/query`

**禁止** `params.sql` / `params.raw_sql`。

```json
{
  "intent": "lead_follow_ups_by_name",
  "params": { "customer_name": "张三" }
}
```

**白名单 intent**（见 `ai/nl2sql/metadata.py`）：  
`lead_detail_by_name`, `lead_follow_ups_by_name`, `leads_by_status`, `pending_leaves`, `daily_reports_recent`。

**限制**：`MAX_ROWS=50`；写操作不允许。  
**权限**：`leads_by_status` 在带 `X-Employee-Id` 时默认过滤 `owner_employee_id`。

---

## 5. 指令式写操作 `modules/enterprise_ops` — 前缀 `/api/v1/enterprise`

### POST `/api/v1/enterprise/commands`

**action 枚举**（当前代码）：

1. `update_lead_status_by_name`  
   `params`: `customer_name`, `status`, 可选 `lost_reason`

2. `approve_leave_by_name`  
   `params`: `student_name`, `decision` (`approved`|`rejected`), `approver_id`, 可选 `approval_comment`

**缺口**：投诉类 action 未实现；按姓名选单在多条 pending 时不稳定。

---

## 6. 环境变量（与 compose 一致）

| 变量 | 含义 |
| --- | --- |
| `DB_HOST` | 云端 `mysql` |
| `DB_PORT` | `3306` |
| `DB_NAME` | `education_service` |
| `DB_USER` / `DB_PASSWORD` | 上一级 `.env`，勿提交仓库 |
| `UPLOAD_DIR` | 容器内 `/uploads` |

---

## 7. 本地测试记录（待填）

| 接口 | 日期 | 环境 | 输入摘要 | 结果 | 操作人 |
| --- | --- | --- | --- | --- | --- |
| POST /consultant/leads | | 本地 MySQL | | | 刘培阳 |
| … | | | | | |

---

## 8. 规划接口（代码中不存在，勿写入 Dify）

- 组织架构、新人指引 GET  
- `student_score` 录入/查询  
- `student_feedback_ticket` 列表/处理/通知  
- `todo_item` 主动待办  
- 可信 auth 中间件  

*OpenAPI 以运行 `uvicorn app.main:app` 后 `/docs` 为准。*


### 智报中心客户分组明细

`GET /api/v1/reporting/board/customers` 的可选 `metric` 新增 `country`（意向国家）、`education`（学历）、`project`（意向项目），与既有 `channel` 一样必须提供 `bucket`。分组按去除首尾空格后的值匹配，空值统一为“未填写”。沿用现有日期范围、分页及服务端报表权限与组织范围；原有请求和返回字段继续保留。客户明细增加 `intended_country`、`education_level`、`intended_project`，供图表下钻展示。
