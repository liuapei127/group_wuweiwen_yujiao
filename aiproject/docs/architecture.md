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
| consultant | CRM 客户及跟进、注册游客待认领名单、联系记录与顾问补录。公开注册写游客表，显式认领后才可读取联系方式和原件，原始资料与补录快照分别留存 |
| customer_service | 官网公开单轮咨询。使用独立 Dify 应用，接入前核对其知识库与工具权限。现有 CS 分支工作流使用独立 CRM 分发接口，需要先完成相应工具迁移 |
| profile | 游客材料原件及本人进度，顾问资料上传及补录、所持资料的研判查询。保留原始正文，使用已有门户身份与本人资料范围 |
| employee_report | 日报 |
| visitor | 官网游客注册、登录和会话。注册记录保存姓名和联系方式作为顾问后续联系的原始数据。游客 Bearer 有效期一小时，数据库保存摘要 |
| events | 统一维护活动和预约。预约、取消及签到使用同一活动行锁；访客活动列表及预约接口使用游客账号会话；签到限有权限的活动负责人或管理员 |
| statistics | 按日或自然周汇总员工日报提交人数和人次，复用员工门户。已授予汇总读取权限的主管限本人所在部门，管理员可查全体。该模块只读 ENT 的日报表 |
| student_admin | 学生行政、请假提交和审批。提交服务由可信学生身份调用，按班主任分配，并在同一事务中同步 ENT 待办。学生端 HTTP 接入等待学生身份与登录 |
| enterprise_ops | 指令业务编排，调用对应领域能力 |
| organization | 组织、同事目录与联系方式 |
| onboarding | 新人指南 |
| score | 成绩录入、查询、更正 |
| feedback | 学习类投诉分配给班主任，公司类投诉分配给服务端配置的主管，创建时在同一事务生成待办。具备读取权限的主管可查看全部投诉，处理权限仍依工单分配。学生端 HTTP 接入等待可信学生身份 |
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

需求中的 student、teacher、class_management、subject、offer、files，以及未接入的 Agents、RAG 等仍仅提供包/占位文件。auth 已在下述门户扩展中实现，LLM 参数理解通过私有 Dify workflow 接入。占位文件没有可用 API，也不代表完成模型调用、RAG、存储、日志或迁移系统。

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


## 官网游客跟进

部署前按现有库结构核对 004、006、007、008、011。通过门户角色权限管理为负责游客跟进的员工授予 `visitor-intake:read` 和 `visitor-intake:write`。认领前的列表提供游客 ID 和注册时间，认领后从「已认领」查看联系方式。电话记录的 `request_id` 应在重试时复用，每次新通话生成新 UUID。保存联系记录后，补录接口自动执行初筛。指定资料 ID 时进度归到该原始提交，未指定时保存到顾问补录项。初筛结果只供顾问查看；CRM 建档由顾问回访确认后发起。


## 员工正式报告工作流

`POST /api/v1/reporting/employee-reports/formal-summary` 接受 `anchor` 日期与 `report_kind`（`daily` 或 `weekly`）。需同时授予日报汇总读取和正式报告生成权限。主管的范围取自服务端的员工部门，管理员可查询全体。周报汇总自然周内的已提交日报。同一员工同一天有多条已提交日报时，正文取 ID 最大的一条。

工作流文件在 `docs/dify/rpt-employee-formal-summary.yml`。配置正式报告应用的独立密钥 `DIFY_EMPLOYEE_FORMAL_API_KEY` 后，服务端发送授权范围内的整理后日报、姓名、部门、事项数据及统计值。工作流会将这些信息发给其配置的模型。原始口述字段留在后端。空白期间直接返回四段无记录说明。生成结果随请求返回。


官网活动入口为前端 /website。游客登录后可预约、取消及查看预约和材料进度。员工活动入口为 /events，按 events:manage 或 events:check_in 显示。活动权限由门户按角色授予。

顾问门户入口为 /visitor-intake。保存通话记录后可以选择已有游客材料或独立补录，初筛符合后，顾问回访并确认意向即可建立关联客户档案。已有通话与建档后的新通话同步到 CRM 跟进历史。部署需应用增量迁移 011。


官网登录入口为 /website。登录后依据服务端身份前往 /website/visitor 或 /website/student。企业后台 /settings/website-accounts 由具备 website-accounts:manage 的员工使用，关联现有企业学生档案。同一档案只能绑定一个官网账号。开通或关闭时撤销旧官网会话并记录员工审计。游客原来的材料、预约和密码仍归原官网账号。学生业务以关联的企业学生 ID 为准。员工工作台 / 按当前职位和权限选择首页，员工认证继续使用现有门户会话。

启用学生身份前需执行待审迁移 009，并为实际操作人员显式授予 website-accounts:manage。已有账号授权后使用原账号重新登录。企业学生档案停用时无法使用学生接口。

官网账号管理也可创建企业学生档案并同时开通原官网账号。新建需选择德国或新加坡、以及具备请假审批和工单处理权限的班主任，复用 sys_user、student_info 和 website_student_access。学生服务读取企业档案中的留学地区。部署前确认已经配置启用的 student 角色。

学生页根据学籍的留学地区显示相应官方政策链接。读不到对应地区时提示确认学籍，不显示另一地区的资料。学生页的「我的材料与活动」复用原官网账号的预约和材料服务，与转为学生前共享记录。

学生端申请进度读取 application_progress，沿用初始化结构。员工页 /application-progress 需 applications:read，新增或更新需 applications:write，均按授权学生范围限制。进度说明和下一步会展示给对应学生。

学生考务从已有 academic_deadline 表读取本人事项和通用事项。默认展示未来七天内开启提醒的待办，时间按北京时间解释。完成操作只对本人事项生效，通用事项仅供查看。

企业考务页 /academic-deadlines 需 academics:read，新增或更正待办理事项需 academics:write，按已授权的学生范围处理。学生首页显示最近即将截止的事项。运行既有 scripts.run_ent_reminders 扫描任务时，七天内即将截止的个人事项会写入学生站内通知。通用事项在首页和考务页展示。

官网登录后可搜索 course_project 中已上架的课程和项目。目录为空时显示空状态，复用已有课程数据。

企业课程管理入口为 /course-management，具备 courses:manage 的员工可维护课程并上下架，继续使用原有 course_project 表。

业务报表入口 /reporting 可查看日报提交统计，及指定日期内创建的 CRM 线索、投诉的当前状态分布。主管按当前归属员工所在部门过滤，管理员统计全库。

心理预警跟进页 /student-alerts 仅读取分派给当前员工且属于其学生授权范围的预警。学生 HTTP 路由无预警入口。跟进动作追加历史，结案后拒绝再次变更。

请假审批和投诉解决在同一业务事务中写入学生站内结果通知。学生只能读取自己的业务结果通知。

老师可手动登记其授权学生的心理预警，同时将观察留档，并按自然周查看本人负责的状态和风险等级汇总。AI 识别待接组员工作流。

海外生活页读取学籍对应国家已启用的 overseas_life_knowledge 条目，支持查询和分页。

官网访客登录后可按国家查看官方留学政策。门户服务指引按当前身份显示可办理事项，讲座回看保留占位入口。

公司类投诉优先分派给已配置且启用的主管。未配置主管编号时，只在存在唯一一个有工单处理权限的在职主管时自动分派。

业务报表和心理预警页可订阅有权读取的统计报表。使用应用数据库配置运行 `python -m scripts.run_ent_reminders --interval 60`。扫描任务按北京时间生成上一个完整自然日或自然周的快照，使用 report_schedule 和 report_generation。改变部门或缩小学生范围后，对应旧快照不再展示。

正式 AI 日报、周报生成成功后写入 report_generation，保存四段总结、提交统计和生成时的成员范围，和定时快照共用报表归档入口。归档 PDF 根据当期归档内容导出，查看和下载均查验生成者和当前权限。


## 企业助手的对话业务

ENT Chatflow 抽取动作与参数。FastAPI 履行员工身份校验、授权查数、候选编号校验和写入确认。按姓名审批请假时只列出分给当前用户的待审批单据。客户跟进总数由数据库计算。主管日报与报表页使用同一组织授权，打开历史对话时重新检查已展示员工的可见范围。聊天录音共用 Dify 转写服务，转写可核对和编辑后发送，写操作仍需确认。

## BASE 本地统一认证

员工门户可使用 `base_rs256` 模式。受保护的员工路由读取当前数据库权限。同一进程使用独立的 RS256 或旧门户验证路径，员工的现有业务权限、班主任关系和学生授权继续由后端计算。浏览器 Access 保存在内存中。刷新与退出使用同源校验、双提交 CSRF 和 HttpOnly 刷新 Cookie。本机仅按环回配置使用本地 Cookie 名称，HTTPS 部署使用安全前缀。

本机启动需配置 `EMPLOYEE_IDENTITY_MODE=base_rs256`、`BASE_PORTAL_ORIGIN` 和仓库外私钥文件 `BASE_JWT_KEYS_FILE`。仅环回 HTTP 调试设置 `BASE_LOCAL_INSECURE_COOKIES=true`。启动后检查 `/api/v1/auth/status`。原门户 HS256 进程保留给过渡使用。

组织管理走员工权限 `organizations:manage`，用 `PUT /api/v1/enterprise/organizations/memberships/{user_id}/{org_id}` 写入成员关系和主部门。组织键来自当前组织表，时间使用 UTC。主管在 BASE 模式下按所管组织和下级的实际有效成员查询报表。旧文本部门不自动转换为成员授权。既有提醒进程每小时做一次 BASE 员工和服务会话、到期服务旧凭证及过期主部门清理。

机器客户端由 `python -m scripts.manage_base_service` 建立、轮换或停用，初始密钥写入指定的新文件。机器使用 `POST /api/v1/auth/service-token`，服务 Access 与员工 Access 分开验证。换票只有既定设计约定，当前没有批准的调用策略或路由。

签名密钥正常轮换时，用新 `active` 密钥签发，旧密钥设为 `verify_only` 并移除私钥，60 分钟后设为 `disabled`。发现泄露时立即在所有进程的密钥配置中禁用该 `kid`，等待已在执行的旧签发请求退出，再运行 `python -m scripts.revoke_base_kid <kid>`。命令按签名历史撤销员工会话、刷新家族和服务会话。发生中断时可重跑。

## 官网栏目管理

`visitor/content_*` 提供官网栏目和卡片管理。管理员可编辑栏目名称、卡片标题和正文、排序与发布状态。公开首页从 `GET /api/v1/website/sections` 读取发布内容，和 Dify 客服知识库分别维护。

## 智报中心

现有 React 工作台提供智报看板。统计、归档及下载沿用 BASE 授权和现有扫描进程。员工日报与独立周报共用原员工入口。学生自评和关怀请求通过官网学生身份提交，员工只处理授权学生范围内的个案和周报。投诉和心理 AI 摘要仅发送群体汇总数字。员工主管可主动比对已授权员工的日报与周报正文、关键进展，并核验结果。报表 AI 默认复用已发布的 Dify RPT 工作流，也可使用指定的独立模型。

## 官网客服

官网客服使用服务端生成的会话编号，访客登录会话绑定网站账号。Dify 负责七意图分流和四库检索。项目推荐与活动筛选读取已发布业务数据。报名在登录后的官网客服完成，选场后由用户确认，FastAPI 复用既有预约服务及其名额与重复报名保护。
