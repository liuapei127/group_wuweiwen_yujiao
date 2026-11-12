# 40 GPT 致 Cursor 当前 ENT 项目进度与接手说明

日期：2026-11-11
项目根目录：D:\Project course\group_wuweiwen_yujiao
交付主目录：aiproject。backend 为历史参考，不是当前交付入口。
负责人范围：刘培阳的 ENT 企业智能助手。本文不是其他小组成员模块的完成报告。

## 1 请先看这个结论

ENT 已从“客户管理较完整，另有五项未开发”推进到“原有接口权限已加固，五项功能均有本地后端第一版”。五项指组织查询、新人指引、成绩、投诉处理、主动待办。

当前证据是 Python 3.13 下 30 项隔离测试通过，不能写成全系统完成、生产身份通过、Dify 接通或腾讯云发布成功。仍缺公共认证、真实 MySQL 验证、实际资料录入、Dify 工作流与跨模块联调。

请不要继续沿用《企业智能助手-ENT未完成功能清单-供GPT参考.md》中“五项完全没有代码”的旧状态，也不要覆盖本轮代码重新生成。先读本文、37、39，再检查实际源码。

## 2 ENT 需求逐项进度

| 任务 | 已实现的本地后端行为 | 尚缺或尚未验收 |
| --- | --- | --- |
| ENT-01 客户录入 | 字段校验、创建客户、负责人一致性校验 | 可信身份、正式入口回归、Dify 文字/语音抽取和追问、重复客户规则 |
| ENT-02 客户档案与跟进 | 分页列表、详情、PATCH 档案、保存跟进；历史 P2 隔离 HTTP 已获限定阶段认可；本轮按名查询限定本人范围并拒绝重名 | 新源码的 MySQL 回归、Dify 重名选择、真实身份及云端验证 |
| ENT-03 客户状态 | 状态机、负责人校验、流失原因；按名指令限定本人名下 | 对话确认、真实身份回归、独立审计需求待定 |
| ENT-04 口述日报 | JSON 提交/更新；本轮拒绝提交他人日报 | 语音转写、字段抽取、提交确认、Dify E2E；RPT 字段约定 |
| ENT-05 管理查日报 | 按日期查询；现阶段默认仅本人，越范围返回 403 | 部门查询、主管下属范围未实现，不得把本人查询宣称完整管理查阅 |
| ENT-06 组织与同事查询 | 新增启用组织关键词查询；员工姓名与部门目录；联系方式需权限 | 实际组织/人员数据、Dify 对接；职能介绍当前表无专用字段 |
| ENT-07 新人指引 | 新增指南录入、分类/关键词检索、编辑权限 | 真实指南整理录入；Dify 有依据问答；当前非向量 RAG |
| ENT-08 成绩 | 新增录入、按学生/学期查询、成绩更正、学生有效性检查和范围权限 | 课程成绩量表、考试唯一性/去重规则、更正历史、学生端接口及联调 |
| ENT-09 请假审批 | 指定审批人列表/审批；条件更新防重复；同名学生和多张待审批单返回冲突 | 可信审批分配契约、真实 MySQL 并发、STU 提交和结果通知联调 |
| ENT-10 投诉处理 | 新增本人被指派工单查询；pending→processing→resolved→closed；解决说明校验、条件更新 | STU 提交/可信分配、学生结果展示与通知；不擅自设置 is_notified=1 |
| ENT-11 口语查库 | 五个白名单意图；本轮全部绑定员工范围，禁止覆盖范围与传 SQL；真实 4xx | 真实身份、主管范围、Dify 抽取与联调、真实 MySQL 验证 |
| ENT-12 指令式操作 | 仍为两种 action：按名改客户状态、按名批请假；本轮加范围、重名拒绝和明确审批决定 | Dify 选择具体 ID 和确认；新增投诉操作目前通过专用接口，未扩展 commands action |
| ENT-13 主动待办 | 新增本人待办创建/查询/完成/取消；独立扫描器；请假/投诉生成待办；到期生成去重站内通知 | 启动部署任务、界面展示/轮询、外部渠道投递、业务结案/转派同步、日报催交规则 |

状态解释：已写代码、已有测试、已部署、已验收四者分开记录。表中“新增”不是整条用户链路验收。

## 3 本轮权限修复是什么

1. 日报写入 employee_id 必须等于当前可信员工 ID；列表默认本人，查询别人返回 403，日期范围非法返回 422。
2. 请假列表只取明确分配给当前员工的单据；未分配单据不开放。审批必须归本人；UPDATE 同时检查 ID、leave 类型、pending 状态与审批人，陈旧更新返回 409。
3. 按姓名找客户必须传 owner_employee_id，在本人范围内匹配；有同名多条返回 409。按姓名审批遇到同名学生或多张本人待审批单也返回 409。
4. 口语查询 leads_by_status、lead_detail_by_name、lead_follow_ups_by_name、pending_leaves、daily_reports_recent 全部绑定当前员工；拒绝范围覆盖及非白名单参数。
5. 请假、NL2SQL、commands 使用 http_fail 返回真实 HTTP 状态码，并保留 code/message/data。原 fail 字典函数保留，未全局改动无关入口。
6. 审批指令不再缺省同意，必须明确提供 decision。

## 4 五项新功能的代码入口

| 路径 | 内容 |
| --- | --- |
| app/modules/enterprise_support/tables.py | 标准 SQL 六张既有表的 SQLAlchemy Core 定义 |
| app/modules/enterprise_support/router.py | 组织、同事、新人指引、成绩、投诉、待办和通知接口 |
| app/modules/enterprise_support/reminders.py | 来源扫描、到期待办提醒和重复扫描去重 |
| scripts/run_ent_reminders.py | 独立扫描任务，支持单次和循环运行 |
| tests/test_ent_access_boundaries.py | 上一批授权修复回归 |
| tests/test_ent_support.py | 本轮五项扩展功能场景测试 |
| app/router_registry.py | 已注册新增路由 |
| app/core/auth/dependencies.py | EmployeePrincipal 新增 permissions、student_ids，默认空集合 |
| app/modules/student_admin/models.py | SysUser 增加 department、contact_info 映射，用于目录查询 |

所有新增业务路径前缀 /api/v1/enterprise：

- GET /organizations
- GET /organizations/colleagues?name=...
- GET /colleagues/{employee_id}/contact
- GET、POST /onboarding-guides
- POST、GET /scores；PUT /scores/{score_id}
- GET /tickets；GET、PATCH /tickets/{ticket_id}
- POST、GET /todos；PATCH /todos/{todo_id}
- GET /notifications

请求字段与限制详见 39 和运行时 /openapi.json。请勿擅自改成 /api/v1/ent 前缀。

## 5 BASE 和跨模块需要提供什么

### BASE 认证

require_employee 仍默认拒绝，trusted_jwt 尚未实现。EmployeePrincipal 现在包含：employee_id、permissions、student_ids。权限和学生范围必须由可信服务端认证/授权逻辑提供，不能从请求 Body 或模型输出直接采信。

当前权限字符串：guides:write、directory:contacts、scores:read、scores:write。成绩操作还必须学生在 student_ids 中。普通员工默认没有这些额外权限。部门、主管与角色映射未实现，不能拿这些字段占位冒充公共 auth。

### STU

请假需要可信服务端指定 approver_id；投诉需要可信分配 assignee_id。学生不能随意选择审批人/处理人。STU 负责提交和结果可见/通知链，ENT 负责授权范围内的处理。投诉处理将 is_notified 重置为 0，未调用实际通知通道，不允许虚报通知完成。

### RPT

日报 key_progress、risks、next_plan 格式、汇总时区和读取授权待共同确认。ENT 日报数据可作为输入，不代表报告生成已接通。

### CS 和 PF

“客服转 CRM、研判自动关联客户”仍是产品待定可选链路。已有客户表字段不代表交接接口已实现。本轮未开发客服转交、自动分配、PF 画像关联接口，不将其默认为 ENT 独自必须交付项。

## 6 待办通知的实际边界

本轮没有启动常驻任务，没有触碰云端。部署方未来在配置正确的 aiproject 环境运行：

python -m scripts.run_ent_reminders --once

或：

python -m scripts.run_ent_reminders --interval 60

脚本会真实读写业务库，接手后不要未经环境核实就对共享库运行。现有源码使用来源行锁和存在性检查去重；SQLite 已测重复执行，MySQL 并发还未验。

站内通知存 notification_log，channel=system。status=sent 仅指通知已入站内信箱，可由 /notifications 查询，不代表手机、微信或邮件送达。

目前未实现源业务完成/转派自动同步待办；待办延期后多次提醒、可靠投递重试、日报催交、外部通知也未实现。不能把本轮称作完整主动推送交付。

## 7 测试和环境证据

- 本机已安装 Windows Python 3.13.16；项目解释器 aiproject/.venv313/Scripts/python.exe。
- 35：Windows 安装、依赖及当时 5 项单元测试证据。
- 36：权限修复后 24 项测试通过。
- 38：五项扩展后 30 项测试通过，退出码 0；包含之前 24 项，不能相加成 54 项。
- 本次编写交接文档时重算了 38 中列出的 8 个源码/测试文件 SHA256，与记录一致；没有为改文档重复执行测试。
- 测试为隔离 SQLite + FastAPI TestClient/ASGI，使用依赖覆盖模拟身份，不是真实 TCP HTTP、MySQL、JWT、Dify 或云验收。
- 有一条 Starlette/httpx 弃用提示；未因该提示修改依赖。
- 34 的 Docker Python 3.13 安装构建证据属于当时源码；新增这批代码之后尚未重建镜像，不得沿用旧构建结果覆盖当前版本。
- 历史 P2 限定阶段签收维持，但仅绑定历史源码与样本；当前新增和修改源码不能引用旧 7 文件指纹冒充完成回归。

## 8 腾讯云状态必须如实写

用户此前自行操作云终端，确认原运行 Python 3.11.18；修改了云端 Dockerfile 至 python:3.13-slim，以及 pyproject 的版本要求。默认 docker compose build api 曾返回 no such service: api，随后已指导显式合并三个 Compose 文件。

截至本交接没有收到云端构建成功、替换容器、版本和健康检查全部通过的证据。不能写云端 Python 3.13 或新增业务已部署成功。也不能只凭历史文档保证云端此刻只有哪些路由，必须实际核查。

## 9 给 Cursor 的下一步任务

1. 先检查当前工作区差异和 38 指纹，保留现有修改，不覆盖、重置或重新清库。
2. 审查五项第一版接口与标准 SQL 的兼容性，重点验证真实 MySQL 自动 ID、类型、事务、审批/工单冲突、扫描并发去重和批量推进。
3. 补当前缺的业务规则：成绩量表/考试标识与更正历史；主管数据范围；投诉与请假可信分配；业务结案/转派后的待办同步；通知渠道与投递语义。
4. 接公共可信身份，使用真实凭据验证伪造、停用、越权和范围；继续默认拒绝，禁止恢复不可信员工头放行。
5. 准备真实组织与新人资料，以授权管理接口导入，不编造公司制度。
6. Dify 做参数抽取、重名选择 ID、审批决定确认、失败处理；收到 4xx、503 或业务失败不回复成功。
7. STU、RPT 两两联调后，在确认的部署环境重建镜像并归档源码版本、测试输出和云端结果。

不要再次要求重发 11 号全文，不使用 13 号 exit 0 作总验收，不因旧问题已关闭继续重复材料循环。新增风险和待办请给出具体文件、触发条件和测试结果。

## 10 阅读顺序

40 当前交接总览 → 37 权限修复说明 → 39 五项功能说明 → 36/38 测试证据 → 实际源码。

旧《ENT未完成功能清单》《需求符合性表》《组会汇报》等尚有过时段落，需按本交接与实际代码更新，历史执行日志不要改写。
