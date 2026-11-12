# 11 · 致 GPT — 企业智能助手（客户管理）评审回应正文

**提交人角色**：企业智能助手（ENT）模块开发（文档中刘培阳）  
**工程路径**：仓库内 `aiproject/`（云端骨架：`/home/ubuntu/education-service/aiproject`）  
**回复日期**：2026-11-11  
**对应任务**：`1-GPT评审与修复任务-原文.md`（客户管理 E2E 评审与修复）  
**配套材料**：本目录 `0`～`10` 号文档（索引见 `0-文件索引与阅读顺序.md`）

---

## 一、开场说明

感谢 GPT 对 R1 交付物的评审。我们认可评审结论：**本地业务读写有效，但不能等同于权限合格、HTTP 联调合格、与标准库结构一致、或云端/Dify 验收通过**；特别是 R1 报告中「未绕过鉴权」的表述**不准确**，已作废。

本文是我们就该评审给出的**正式书面回应**（可直接作为对话首条消息发给 GPT）。更细的代码对照、接口字段、历史 R1 记录见同目录其他编号文件。

---

## 二、对评审要点的逐条回应

### 2.1 鉴权与权限（必须项 — 已改代码，待 HTTP 复测）

| GPT 要求 | 我们的处理 |
| --- | --- |
| 状态更新不得在无身份时成功 | 已实现 `require_employee`：须 `Authorization: Bearer <token>` 且配置 `AUTH_BEARER_TOKEN`，并携带合法 `X-Employee-Id` |
| 未配置 token 不得静默放行 | 未配置 `AUTH_BEARER_TOKEN` 时业务接口返回 **503**（服务未就绪），非 200 |
| 无/错 Bearer | **401** |
| 改他人负责的客户 | **403**（HTTP 状态码，非 200+body code） |
|  consultant 全路由保护 | 录入、列表、详情、状态、跟进均 `Depends(require_employee)` |

**如实边界**：当前仍是**服务间 Bearer + 员工 ID 请求头**的过渡方案，**不是**公共 `modules/auth` / JWT 员工登录。生产级身份契约需与集成负责人对齐后替换；我们**未**添加任何「生产环境绕过鉴权」开关。

**代码位置**：`app/core/auth/dependencies.py`，`modules/consultant` 路由。

### 2.2 HTTP 语义（必须项 — 已改）

业务错误改为标准 HTTP 状态：**404**（不存在）、**403**（无权限）、**409**（非法状态流转）、**422**（校验失败），不再依赖 HTTP 200 包 `code` 表达失败。

### 2.3 测试分层（部分完成）

| 层级 | 状态 |
| --- | --- |
| R1 TestClient + 本地 MySQL 业务闭环 | 已完成（**弱鉴权环境**，仅作历史证据） |
| 单元（状态机） | `tests/test_lead_status_rules.py` 已有 |
| **真实 HTTP**（Uvicorn + httpx） | 脚本 `scripts/run_customer_http_e2e.py` 已提供；需在 `.env` 配置 `AUTH_BEARER_TOKEN` 后执行并落盘记录 |
| Dify Chatflow | **未做** |
| 腾讯云 `api` 服务构建部署 | **未做**（云端目前仍仅 `GET /health`、`GET /health/db`） |

我们同意：**TestClient 不能替代真实 HTTP 联调**；R2 代码改完后，以 HTTP 脚本输出为下一版验收证据（见 `4-E2E验证报告-R2修订版.md` §5）。

### 2.4 标准库表结构（R1 不足 — 本地已补齐 31 表）

R1 仅在本地用 `CREATE TABLE IF NOT EXISTS` 建了 **`crm_lead`、`crm_follow_up` 两张表**，无法声称与团队标准一致。GPT 指出正确。

**2026-11-11 更新（本地开发库）**：

- 已在本地 MySQL 库 **`education_service`** 按标准脚本  
  `教育服务_0914/2222通过表可以实现curd/db_init.sql`  
  重建 **31 张表**（脚本内含 `DROP TABLE IF EXISTS` 后 `CREATE`，与标准字段/索引/COMMENT 一致）。
- 一键复现：`aiproject` 下执行 `python scripts/apply_db_init.py`（读取 `.env` 中 `DB_*`，**不向文档写入密码**）。
- **影响说明**：本地若曾有 R1 测试数据（如 `crm_lead.remark` 标记），会被 DROP 清掉，需用 HTTP E2E 重新造数。
- **未改动**：腾讯云数据库与部署；**未**在云上执行含 DROP 的脚本（仍遵守「不擅自改云」边界）。

31 表清单（与 `db_init.sql` 一致）：

`sys_role`, `sys_user`, `sys_organization`, `profile_rule`, `customer_source`, `customer_profile`, `crm_lead`, `crm_follow_up`, `employee_daily_report`, `report_schedule`, `report_generation`, `student_info`, `student_score`, `student_admin_service`, `student_psych_profile`, `student_psych_record`, `student_psych_alert`, `student_feedback_ticket`, `academic_deadline`, `application_progress`, `course_project`, `event_lecture`, `event_registration`, `knowledge_base`, `overseas_life_knowledge`, `chat_session`, `chat_message`, `intent_config`, `notification_log`, `onboarding_guide`, `todo_item`.

CRM 两表与标准逐字段对比见 `7-crm表结构对比-db_init.md`（**本地全量建表后**，「缺 29 表」项已不成立；索引/COMMENT 以 `db_init.sql` 为准）。

### 2.5 工程与配置

| 项 | 说明 |
| --- | --- |
| `pip install -e .` | 已调整 `pyproject.toml`（readme/setuptools）；**干净 venv 复验输出待补** |
| 环境变量 | 应用使用 `DB_HOST/PORT/NAME/USER/PASSWORD`、`UPLOAD_DIR`、`AUTH_BEARER_TOKEN`（非 `MYSQL_DATABASE` 命名） |
| `config.py` vs 云端 `config/` 包 | 本仓库单文件 `app/core/config.py`；与云端目录结构合并由集成负责人决定，我们未覆盖云端 |
| Docker build | 本轮未在本地容器内复验 |

### 2.6 业务范围（未越界）

本轮**仅**客户管理（consultant）与认证/HTTP 修复；**未**实现成绩/投诉/组织架构/onboarding/todo 等模块 API；**未**配置 Dify；**未**执行云侧 `docker compose ... up -d --build --no-deps api`。

客户 API 真实前缀：**`/api/v1/consultant`**（非 `/api/v1/ent/...`）。NL2SQL 为 **`POST /api/v1/ai/nl2sql/query`**（只读白名单，与客户管理验收分离）。

---

## 三、R1 与 R2 结论对照（给 GPT 的快速表）

| 维度 | R1 | R2 代码 | R2 测试 / 环境 |
| --- | --- | --- | --- |
| 业务闭环（录入→查→改状态→再查） | TestClient 通过 | 逻辑保留 + 鉴权依赖 | HTTP 脚本 **待跑** |
| 鉴权 | 表述错误（可弱约束改状态） | Bearer + 503/401 + owner 校验 | 待 HTTP 记录 |
| HTTP 错误语义 | 部分 200+code | 4xx 状态码 | 待 HTTP 记录 |
| 库表与标准 | 仅 2 表 | — | 本地 **31 表** 已按 `db_init.sql` 建好 |
| 云端 / Dify | 未做 | 未做 | 未做 |
| 公共 auth/JWT | 未做 | 未做（过渡 Bearer） | 阻塞，待集成契约 |

**一句话**：R1 证明了 ORM 与 MySQL 上的客户主路径；GPT 对权限与 HTTP 的批评成立；R2 已在代码层**默认拒绝未认证请求**并修正 HTTP 语义；本地库已对齐 **31 表标准**；**HTTP 复测证据、Docker、公共 auth、Dify/云端验收**仍待完成。

---

## 四、请你（GPT）重点评审的问题

1. 过渡方案 `AUTH_BEARER_TOKEN` + `X-Employee-Id` 是否与「在公共 auth 就绪前允许 Dify→API 网关联调」的目标一致？还缺哪些头/契约字段？
2. `require_employee` 与 consultant `update_status` 的 owner 校验是否覆盖你关心的越权场景（含跟进写入是否也需同规则）？
3. 本地已执行含 **DROP** 的 `db_init.sql` 仅用于开发库 — 团队在测试/预发应采用的**无 DROP** 迁移策略，你建议如何写进交付说明？
4. `run_customer_http_e2e.py` 的通过标准是否足够作为 R2 的「已测试」依据？还缺哪些负例（503/401/403/409）？

---

## 五、我们承诺的下一步（可追踪）

1. 在 `.env` 设置本地随机 `AUTH_BEARER_TOKEN`（不提交 Git）。  
2. 运行 `python scripts/run_customer_http_e2e.py`，将结果整理为 `10-HTTP-E2E测试记录.md`（手机号等脱敏后再外发）。  
3. 把 HTTP 记录与本文件一并发回 GPT 做 R2 测试层签收。  
4. 与集成负责人对齐公共 auth 后，替换 Bearer 过渡方案（时间表不在本回复中虚构）。  
5. 云侧构建部署仅在团队合并与负责人安排后进行，使用约定 compose 文件与 `--build --no-deps api`。

---

## 六、材料索引（避免重复粘贴）

| 序号 | 文件 | 用途 |
| --- | --- | --- |
| 3 | `3-GPT评审回应与修复清单-R2.md` | 修复项与代码对照表 |
| 4 | `4-E2E验证报告-R2修订版.md` | 当前有效 E2E 叙事（R1 鉴权段作废） |
| 5 | `5-企业智能助手-需求符合性表.md` | 四态符合性 |
| 6 | `6-企业智能助手-API接口文档-客户管理-R2.md` | 路由与请求头 |
| 7 | `7-crm表结构对比-db_init.md` | CRM 与标准 SQL 差异（全库背景见本文 §2.4） |
| 8 | `8-认证与测试分层说明.md` | 什么算通过 |
| 9 | `9-测试记录与脚本说明.md` | 脚本路径 |

**推荐给 GPT 的最小附件集**：**本文（11）+ 3 + 4 + 6**；若评审库表，加 **7**；HTTP 跑通后加 **10**。

---

## 七、合规与表述自律

- 共享文档与 GPT 对话中**不出现**完整手机号、数据库密码、`AUTH_BEARER_TOKEN` 实值。  
- 不测云端凭据，不扫描猜测生产密码。  
- 新 E2E 标记建议使用运行时刻 `E2E_HTTP_YYYYMMDD_HHMMSS`，避免与历史标记 `E2E_TEST_20260311` 混用造成日期歧义。

---

**结语**：我们接受 GPT 对 R1 的否定性结论，并已在 R2 代码与本地 **31 表** 环境上落实可验证的改进；愿在 HTTP 复测材料补齐后，请你做第二轮签收，并指明过渡鉴权与公共 auth 切换时仍须满足的清单项。
