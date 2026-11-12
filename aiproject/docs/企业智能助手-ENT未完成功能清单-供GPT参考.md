# 企业智能助手（ENT）· 未完成功能清单

> **用途**：供 GPT / 组内评审对照需求，明确刘培阳负责模块的缺口与优先级。  
> **负责人**：刘培阳  
> **代码根目录**：`aiproject/`（`consultant`、`employee_report`、`student_admin`、`enterprise_ops`、`ai/nl2sql`）  
> **需求依据**：`docs/教育服务AI-全系统产品需求说明书.md`、`教育服务_0914/.../开发引导.md`（ENT-01～13）、`客户需求表.xlsx` 企业智能助手 B/C 列  
> **状态依据**：`aiproject/docs/企业智能助手-需求符合性表.md`、`企业智能助手-组会汇报-进度与需求大白话.md`（截至 2026-11-11）  
> **关联文档**：`客户管理-Dify闭环说明.md`、`回复Cursor/04-认证阻塞项与契约待决.md`

---

## 0. 范围说明

本文只盘点 **ENT 模块**（企业智能助手），不含 PF/CS/STU/RPT 的完整交付，但会标注 **跨模块依赖**（木合塔尔 STU、夏登东 RPT、BASE 鉴权/集成）。

**交付判断维度**（不得混用）：已实现｜已测试｜已部署｜已验收。

**当前总阻塞**：`app.main` 未接可信 JWT 时，**所有员工业务 API 默认 HTTP 503**（仅 `/health`、`/health/db` 开放）。云上 api 容器 **尚未 build 进 ENT 业务路由**。

---

## 一、整块未实现（需求有、代码无）

| 任务卡 | 业务场景 | 相关表 | 说明 |
| --- | --- | --- | --- |
| **ENT-06** | 组织架构查询 | `sys_organization`, `sys_user` | 无专用 GET；Dify 未接 RAG/API |
| **ENT-07** | 新人指引 | `onboarding_guide` | 无 API；素材 `公司信息/公司新人指南.docx` 未入库 |
| **ENT-08** | 成绩录入与查询 | `student_score` | 无模块与读写 API；非「列表+状态」简版 |
| **ENT-10** | 投诉跟进 | `student_feedback_ticket` | `app/` 下 **无路由**；提交→处理→解决说明→学生可见 **全链路未做** |
| **ENT-13** | 主动待办推送 | `todo_item` 等 | 无定时扫描、无待办 GET、无推送 |

文档约定：**06/07/08/13 可标为后期**；**10 强依赖 STU-03/04**，但 ENT 侧 API 仍为零。

---

## 二、有 API 但业务未做完

### 2.1 客户管理 ENT-01～03（`modules/consultant`）

| 缺口 | 现状 |
| --- | --- |
| **Dify 闭环** | 《客户管理-Dify闭环说明》四步（录入→查库→跟进→状态）**未验收**；企业 Chatflow **未建完/未验** |
| **语音录入** | 需求为语音/文字；后端只收 **已结构化 JSON**；Dify 语音链未打通 |
| **去重/撞单** | 无统一重复客户规则 |
| **重名消歧** | 按姓名常只命中一条；详情/改状态需 **lead_id 澄清**（NL2SQL/列表消歧待加强） |
| **可信操作人** | 须 JWT 得 `employee_id`；历史 `X-Employee-Id` 不可用于生产验收 |
| **状态审计** | 无独立审计表（若答辩要追溯需补） |

**已有 OpenAPI（本地代码）**：

- `POST /api/v1/consultant/leads`（ENT-01）
- `GET /api/v1/consultant/leads`、`GET .../leads/{id}`、`POST .../follow-ups`（ENT-02）
- `PATCH /api/v1/consultant/leads/{id}/status`（ENT-03）

### 2.2 口述日报 ENT-04～05（`modules/employee_report`）

| 缺口 | 现状 |
| --- | --- |
| **口述闭环** | `POST /api/v1/employee-reports` 存在；**不能宣称「口述日报完成」**——缺 Dify 转写 + 字段抽取 + E2E |
| **管理查阅** | `GET /api/v1/employee-reports` 存在；**无部门维度**；经理只看下属、角色权限未做 |
| **与 RPT 契约** | `key_progress`、`risks` 等字段格式需与 **夏登东 RPT-02** 书面对齐 |

### 2.3 请假审批 ENT-09（`modules/student_admin` + `enterprise_ops`）

| 缺口 | 现状 |
| --- | --- |
| **STU 联调** | STU-01 写 `student_admin_service`（pending）**未联调** |
| **按姓名审批风险** | `approve_leave_by_name`（ENT-12）易 **误选重名学生** |
| **学生通知** | 审批后 **STU-02 查询/通知** 未验收 |

**已有接口**：

- `GET /api/v1/student-admin/leaves/pending`
- `POST /api/v1/student-admin/leaves/{leave_id}/approve`
- `POST /api/v1/enterprise/commands`（`approve_leave_by_name`）

### 2.4 NL2SQL ENT-11（`ai/nl2sql`）

| 缺口 | 现状 |
| --- | --- |
| **测试/部署** | V1 实现存在；**无系统测试、未上云** |
| **数据权限** | 顾问 vs 经理 **可查范围** 未绑 auth 角色 |
| **与客户查询** | 同名客户场景逻辑偏弱 |

**已有接口**：`POST /api/v1/ai/nl2sql/query`（白名单 intent，禁 raw SQL）

### 2.5 指令式处理 ENT-12（`modules/enterprise_ops`）

| 缺口 | 现状 |
| --- | --- |
| **动作覆盖** | 仅 **2 个** `action`：`update_lead_status_by_name`、`approve_leave_by_name` |
| **投诉等** | 投诉结案及其他写操作 **未接入** |

**已有接口**：`POST /api/v1/enterprise/commands`

---

## 三、全模块共性缺口（不修则整体不算交付）

| 项 | 说明 |
| --- | --- |
| **BASE 统一 JWT** | `modules/auth` / `trusted_jwt` 未合入 → `app.main` ENT 业务 **503** |
| **可信员工身份** | P2 隔离 HTTP 有部分证据；**生产 JWT 验收未完成** |
| **腾讯云 API** | 云上仅 **health**；需 `docker compose ... --build --no-deps api` 合并 `aiproject` |
| **Dify 企业 Chatflow** | 未验收；HTTP `code≠0` 或 4xx/5xx 时禁止回复「已成功」**未配置** |
| **跨模块书面契约** | 请假/投诉/日报与 **木合塔尔（STU）**、**夏登东（RPT）**、**集成（auth）** 见 `04-认证阻塞项与契约待决.md` **待全员确认** |

---

## 四、ENT-01～13 总览表

| 任务卡 | 后端代码 | 还缺什么（ENT 负责人视角） |
| --- | --- | --- |
| **01～03** 客户 | ✅ | Dify 闭环、语音/去重/重名、JWT、上云、验收 |
| **04** 口述日报 | ✅ 接口 | Dify 语音→JSON、测试、上云 |
| **05** 管理查日报 | ⏳ | 部门维度、经理权限、RPT 字段契约 |
| **06～07** 组织/新人 | ❌ | 灌数 + API 或 Dify 知识库 |
| **08** 成绩 | ❌ | 完整读写 + 校验 |
| **09** 批请假 | ⏳ | STU 联调、按名审批改进、通知闭环 |
| **10** 投诉 | ❌ | 全 API + STU 字段/状态机对齐 |
| **11** NL2SQL | ✅ V1 | 数据范围、测试、上云、解除 503 |
| **12** 指令 | ⏳ | 扩展 action（含投诉等） |
| **13** 待办 | ❌ | 定时任务 + `todo_item` + 推送 |

图例：✅ 本地大致有代码；⏳ 部分；❌ 未做。

---

## 五、跨模块依赖（须书面确认）

| 链路 | ENT 方 | 对方 | 契约缺口 |
| --- | --- | --- | --- |
| 请假闭环 | 审批 API、commands | STU：提交、结果通知 | `student_id`、单号 ID、审批人角色 |
| 投诉闭环 | 处理 API（待开发） | STU：工单、通知 | 状态枚举、`is_notified`、解决说明 |
| 日报汇总 | `employee_daily_report` | RPT-02 | `key_progress` / `risks` 格式 |
| 心理高危 | 企业介入入口未定 | STU-09 | 谁接收 `student_psych_alert` |

---

## 六、建议补齐顺序（与《需求符合性表》D 节一致）

1. **BASE**：JWT 落地 → `main` 解除业务 503 → Dify 带 `Authorization`。
2. **客户第一条 Dify 闭环**：本地 MySQL 四态打勾（《客户管理-Dify闭环说明》）。
3. **与 STU 契约确认后**：请假 E2E；再开发 **ENT-10**。
4. **与 RPT 契约确认后**：固化日报字段；加强 ENT-05 部门查询。
5. **集成上云**：build api 镜像，云端回归。
6. **可延期并写入需求说明**：ENT-06/07/08/13。

---

## 七、路径与常见纠错

| 错误说法 | 正确说法 |
| --- | --- |
| `/api/v1/ent/nl2sql/query` | `POST /api/v1/ai/nl2sql/query` |
| HTTP 节点数 = 完成 | 须含路由、追问、身份、失败处理、**库中可核对** |
| 口述日报 = POST 能调通 | 须 Dify 语音/抽取 + 字段契约 + E2E |
| 全塞进 `consultant` | 已拆：`consultant` / `employee_report` / `student_admin` / `enterprise_ops` / `nl2sql` |
| PF 上传简历 = ENT 录客户 | PF：`customer_source`；ENT：`crm_lead`，不同入口 |

---

## 八、一句话结论（给 GPT 的上下文）

ENT **核心 CRM、日报 POST/GET、请假审批骨架、NL2SQL V1、2 条 enterprise commands** 在 **本地 `aiproject` 大致已有**；**组织、新人、成绩、投诉、主动待办、Dify 企业流验收** 仍缺；已写部分还欠 **可信登录、Dify 闭环、上云、跨模块契约**——按需求表仍属 **未完善 / 未验收**。

---

## 九、仓库内延伸阅读

| 文档 | 路径 |
| --- | --- |
| 全系统需求 | `docs/教育服务AI-全系统产品需求说明书.md` |
| 需求符合性（正式表） | `aiproject/docs/企业智能助手-需求符合性表.md` |
| 组会大白话 | `aiproject/docs/企业智能助手-组会汇报-进度与需求大白话.md` |
| 客户 Dify 闭环 | `aiproject/docs/客户管理-Dify闭环说明.md` |
| API 清单 | `aiproject/docs/企业智能助手-API接口文档.md` |
| 认证阻塞 | `aiproject/docs/回复Cursor/04-认证阻塞项与契约待决.md` |
| 路由注册真相源 | `aiproject/app/router_registry.py` |

*文档版本：v1.0 · 2026-11-11 · 由 Cursor 根据组内状态整理，供 GPT 续写评审/计划用。*
