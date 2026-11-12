# 项目目录与分层约定

依据用户提供的《需求.md》，于 2026-11-11 落地。此文约束后续开发，功能进度另见交接记录。

## 基本布局

- **frontend/**：ENT 企业智能工作台（Vite + React + Ant Design），本地联调见 `docs/ENT-企业工作台-开发联调说明.md`。
- app/main.py：应用装配；router_registry.py：路由注册；model_registry.py：已实现表模型注册。
- app/core/：config、database、security、middleware、exceptions、responses、logging、storage。
- app/modules/：业务模块。
- app/ai/：llm、agents、workflows、tools、memory、rag、nl2sql、prompts。
- app/shared/：constants、utils、types；app/legacy/：历史兼容预留。
- scripts/：运维和开发脚本；tests/：modules、ai、integration、e2e。
- docs/、data/uploads、data/knowledge、data/datasets、migrations/、html/、logs/。

## 业务模块分层

| 文件 | 职责 |
| --- | --- |
| router.py | 参数绑定、调用 service、HTTP 响应；不直接执行 SQL |
| schemas.py | 请求和响应结构、字段格式校验 |
| models.py | SQLAlchemy ORM 模型或 Core Table 定义 |
| repository.py | SQL 查询和数据读写，不决定业务权限或自行提交新模块事务 |
| service.py | 业务规则、授权检查、状态流转、事务编排 |

新功能不得再集中到一个 router.py。已有 consultant、employee_report、student_admin 保留其业务实现和兼容行为；旧模块中事务位置、HTTP 异常依赖等更细规范可在明确需求下逐步统一，不将它们冒充本次重写内容。

## 本次业务域划分

| 模块 | 职责 |
| --- | --- |
| consultant | CRM 客户及跟进 |
| employee_report | 日报 |
| student_admin | 学生行政、请假审批 |
| enterprise_ops | 指令业务编排，调用对应领域能力 |
| organization | 组织、同事目录与联系方式 |
| onboarding | 新人指南 |
| score | 成绩录入、查询、更正 |
| feedback | 反馈工单与投诉处理 |
| todo | 待办、站内通知、后台提醒 |
| system | 健康检查 |
| auth | 员工登录、JWT 会话、角色权限、学生授权与审计。8000 默认 blocked；门户进程显式 trusted_jwt |
| portal | 工作台统计、按权限生成的功能目录、授权学生与健康状态。无独立业务表 |
| ai/assistant | 私有 Dify 只抽取参数；确认、取消和业务调用由后端以员工 JWT 执行 |

organization、onboarding、feedback、todo、employee_report、student_admin、enterprise_ops 是按当前 ENT 业务补充的模块，沿用框架的模块分层。没有为了目录示例更改 API 前缀。

## 兼容与注册

core/config、database、responses 由单文件改为包，原 app.core.config 等导入路径仍有效。员工认证实现入口移至 core/security；core/auth 仅重导出同一函数和身份类型，以保持依赖覆盖对象一致。

enterprise_support/router.py、tables.py、reminders.py 为旧调用方保留兼容导入，不承载新增逻辑，也不在生产路由注册中重复挂载。

模型统一使用 app.core.database.Base.metadata，register_models() 只导入模型，不执行 create_all 或数据库连接。新增模型必须显式加入注册表。

## 预留部分

需求中的 student、teacher、class_management、subject、offer、statistics、files，以及未接入的 Agents、RAG 等仍仅提供包/占位文件。auth 已在下述门户扩展中实现，LLM 参数理解通过私有 Dify workflow 接入。占位文件没有可用 API，也不代表完成模型调用、RAG、存储、日志或迁移系统。

tests/repro 是既有隔离复现工具，继续保留。新增测试按四类目录存放；SQLite/ASGI 测试归 integration，不标记为真实 E2E。

## 异常与无持久化模块

新业务 service 使用 core/exceptions 中的 BusinessError，公共异常处理器负责映射 HTTP 状态和响应；enterprise_ops 返回 CommandResult，由 router 包装响应。状态码及历史错误响应格式保持原样。

enterprise_ops 属于跨业务编排，不拥有独立数据表，因此不创建空 models/repository；调用已有领域的 service/repository。system 的健康检查同样不创建虚假业务表。其他没有业务实现的框架预留模块不机械生成五个空文件。

## 2026-11-11 并发与业务一致性扩展

成绩新增 identity.py 规范考试标识和提交指纹，models.py 同时注册 student_score_history；service 负责唯一冲突、版本、更正与历史事务，repository 负责读写。待办同步业务位于 todo/synchronization.py，行锁及写入位于 sync_repository.py，定时批次与通知查询位于 reminder_repository.py。请假事务已从 repository 移至 service，与待办同步一起提交。

增量迁移位于 scripts/migrate_ent_reliability.py 和 migrations/001_ent_reliability_expected.sql。真实多进程测试只允许 ent_verify_ 前缀的独立本机库，入口 scripts/verify_ent_concurrency.py。

## 2026-11-12 Dify 回归修复

AI 的纯动作/确认/结果契约位于 app/ai/workflows/ent_contracts.py，scripts/build_ent_chatflow.py 据此生成 Dify DSL；业务校验仍由所属模块 service 执行。actor 字段缺省时只能由 router 从可信 principal 推导，保留显式字段的权限检查和默认拒绝。todo/reminder_repository.py 的 scanner_lock 在 MySQL 用独立连接持有数据库级扫描锁到事务结束，扫描候选读取与源记录行锁仍在 repository。


## 2026-11-12 员工门户、RBAC与AI扩展

- frontend/：官方Vite React/TypeScript脚手架与Ant Design；菜单/按钮按服务端permissions展示，路由直达也受前端权限守卫保护，最终访问权限由后端校验。
- app/modules/auth/：schemas处理登录及账号/角色输入；repository负责既有sys_user/sys_role和认证扩展表；service负责密码、JWT会话、实时角色授权和管理事务；router仅绑定HTTP输入输出。
- app/modules/portal/：聚合工作台统计、权限功能目录、授权学生及健康状态。没有独立持久化表，不创建虚假的models；统计SQL在repository。
- app/ai/assistant/：私有Dify仅抽取动作与参数；员工JWT不传给Dify。会话、待确认动作、版本和消息在本地持久化；确认/取消由服务端控制，再以原员工身份调用固定本机业务API，继续执行RBAC、归属与学生范围检查。
- app/core/security/：Argon2密码哈希、严格JWT校验及数据库会话撤销；rbac.py定义功能目录、初始角色模板及接口映射。权限不是由浏览器或模型提供。

002迁移仅新增ent_auth_role_permission、ent_auth_student_scope、ent_auth_session、ent_auth_login_attempt、ent_auth_audit、ent_ai_conversation、ent_ai_message七张扩展表，复用sys_user和sys_role，不在应用启动时迁移。初始角色模板可由管理员调整，不代表未确认的公司制度；所有角色继续受数据归属和学生授权范围约束。

原8000进程默认blocked，用于既有Dify Chatflow拒绝场景；门户8002进程显式启用trusted_jwt，5173代理到8002。私有门户意图工作流与公开32节点Chatflow分开。服务端密钥保存在忽略的.env，凭据及失败trace同样不进入版本控制。

门户验收入口：scripts/verify_ent_portal_http.py（四角色、权限/菜单、接口403、退出失效），tests/integration/test_ent_portal_routes.py（隔离SQLite与受控配置），frontend/e2e（UI、真实角色联调和独立AI闭环项目）。完整联调步骤见docs/ENT-企业工作台-开发联调说明.md。
