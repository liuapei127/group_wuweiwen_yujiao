# 项目目录与分层约定

2026-11-18 按用户最终确认，部门经理投诉周报仅统计当前所管部门及下级组织成员负责的投诉；即使具备全部投诉工单查看权限，周报也不扩大到全公司。汇总、明细、时效分析、手动及定时归档使用同一部门范围，归档与 PDF 下载每次重新核对范围；旧的全公司投诉报告不允许部门经理下载。没有数据时前端保留图表区域并显示“当前授权范围和所选期间暂无数据”。管理员仍可查看全公司报表。

2026-11-18 员工助手查询展示与流式回复：`ai/assistant/query_results.py` 将已授权的待办、请假、工单、日报等实际响应字段转换为中文明细，不让模型改写业务事实，也不把查询结果送入 Dify。历史原始 JSON 回复在读取时使用同一格式转换。员工消息接口继续支持原 JSON 响应，前端通过 Accept 请求 SSE；Dify Workflow 与 Chatflow 均请求 streaming，只预览闲聊文本，不展示结构化动作或节点调试数据。业务结果和本地回复在回合保存成功后逐段发送，最终 result 事件返回同一已保存会话；确认、版本检查、业务回调及实时授权保持原有流程。

2026-11-18 顾问预约记录：`consultant/intake_router` 新增只读 `GET /api/v1/consultant/visitor-intake/{visitor_id}/reservations`，复用 `visitor-intake:read` 并实时核对当前认领人。`intake_repository` 关联活动、预约与当前认领关系，按预约编号倒序游标分页；返回活动信息、预约状态及预约、取消、签到时间，不返回其他参加者或签到人员资料。前端客户详情及资源池跟进详情复用 `VisitorReservations`，支持刷新和每 30 秒更新；签到与活动管理授权不变，无新增表或迁移。

2026-11-17 管理员授权调整：`admin` 角色固定拥有服务端权限目录中的全部功能权限，已有账号无需补写授权记录，新权限自动纳入。角色保存会将完整权限写入记录与审计；管理角色页面展示全部勾选且不允许缩减。普通角色仍按存储授权及既有角色限制计算。心理周报的全体汇总允许管理员与主管读取，个人业务继续执行所属模块的数据范围检查。账号停用、角色停用、可信身份和最后管理员保护仍生效。

依据用户提供的《需求.md》，于 2026-11-11 落地。此文约束后续开发，功能进度另见交接记录。

## 基本布局

官网客服的近期对话由当前浏览器标签页保存，登录后按登录会话隔离，刷新和切换页面可恢复。登录、匿名两种入口均将最近八条用户和客服消息作为模型上下文，画像较长时优先保留最新对话。清空会开启新客服会话，退出登录会清除该登录会话的浏览器记录，迟到回复不能写回已清除的记录。后端客服会话仍管理活动预约状态。登录后，客服、游客材料与顾问编辑共用已关联的客户画像，建档前的资料按游客账号暂存；浏览器历史只作对话上下文，当前用户自述沿原逻辑更新画像。客服回忆本人姓名和年龄时直接读取当前账号最新保存的资料；匿名年龄回忆只参考浏览器本轮用户自述，未记录时询问补充。客服 Mem0 使用独立的 `CS_MEM0_API_KEY`，仅检索与当前画像一致的事实。客户画像接口通过短时 SSE 通知版本变化，前端重新读取已保存画像。客户详情展示的结构化 JSON 与研判工作流输入一致，每次研判留存输入快照与规则版本。

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

`app/modules/classroom` 管理项目班级、班级班主任、入班及转班历史。每个项目可有多个班级，每个班级指定一名班主任。学生班级决定班主任，所属项目决定留学地区。官网身份开通和入班共用事务；管理员负责入班、转班和更换老师，班主任只读本人名册及详情。转班或更换班主任时同事务交接全部未完成请假、学习投诉、心理预警、关怀个案并同步待办；历史原操作人保留。老师停用或调离岗位、角色停用或移除办理权限前强制检查交接。

`app/modules/teaching` 独立维护预科、语言培训和海外院校教学课程及班级开课，不含价格。管理员配置，班主任在`score`中按班级课程录入并保留更正历史。迁移026增加成绩和考务阶段，旧记录为unspecified并提示核对。考务整班发布保存请求编号和指纹，按班级行锁串行发布及重试。请假证明由`student_admin/attachments.py`处理格式、归属和下载，BLOB不以公开URL暴露。反馈模块保留投诉分类纠正和处理审计。顾问通过其认领关系查看学生申请，班主任负责维护。

员工端心理预警、工单、请假及关怀个案在已有记录权限过滤后，按学生账号 ID 批量补充只读 `student_name`，姓名取自当前学生档案。前端列表使用相邻的“学生编号”和“姓名”两列，详情分别显示两个字段；不新增全体学生查询权限，也不使用姓名匹配记录归属，无对应档案时保留原编号。

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

顾问从 /visitor-intake 认领游客后，系统创建该顾问名下的意向客户。顾问从 /customers 进入客户详情，维护资料与跟进状态并发起研判。游客通话同步到 CRM 跟进历史。学生档案在官网账号开通学生身份时新建或关联。部署和历史数据处理见 migrations/README.md。


官网登录入口为 /website。登录后依据服务端身份前往 /website/visitor 或 /website/student。企业后台 /settings/website-accounts 由具备 website-accounts:manage 的员工使用，关联现有企业学生档案。同一档案只能绑定一个官网账号。开通或关闭时撤销旧官网会话并记录员工审计。游客原来的材料、预约和密码仍归原官网账号。学生业务以关联的企业学生 ID 为准。员工工作台 / 按当前职位和权限选择首页，员工认证继续使用现有门户会话。

启用学生身份前需执行待审迁移 009，并为实际操作人员显式授予 website-accounts:manage。已有账号授权后使用原账号重新登录。企业学生档案停用时无法使用学生接口。

官网账号管理也可创建企业学生档案并同时开通原官网账号。新建需选择项目及该项目下的班级，留学地区取自项目，班主任取自班级。所选班主任需具备请假审批和工单处理权限，复用 sys_user、student_info 和 website_student_access。学生服务读取企业档案中的留学地区。部署前确认已经配置启用的 student 角色。

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

## 客户详情与官网资料协同

顾问认领游客后可记通话。系统管理员在官网账号管理建立或关联已有客户档案，关系继续使用 visitor_intake.crm_lead_id。客户管理按 owner_employee_id 展示名单。员工和官网入口共用资料保存服务，通过资料版本处理并发编辑。导入文件按已有姓名或本人手机号核对归属，文件包含的身份信息须与当前客户一致。有独立核验记录时使用核验记录，其余客户使用当前姓名、联系方式或关联官网登录手机号。明确身份冲突、多客户文件及已核验为其他客户的手机号拒绝导入。缺少可核对身份信息时展示候选属性，游客须确认属于本人，顾问须确认属于当前客户，服务端校验确认后才写入，并在原资料解析结果中记录确认人、时间及匹配依据。预览绑定客户、上传人和版本，确认时重新核对身份与版本。客户详情可直接识别游客已上传的附件或文字资料。原材料导入使用现有来源编号，确认时再次核对归属、文件内容和资料版本，并更新为已导入。正式研判先保存规则结果，再结合对应资料快照生成 Dify 建议与话术，失败时规则结果保留。


客户和顾问的已导入资料列表共用当前客户的已确认来源。文件名可打开资料正文，PDF 原件在弹窗预览，其他文件可下载原件。资料详情和附件接口每次核对本人账号关联或顾问归属及 crm:read 权限，读取 customer_source 或 visitor_material 中保存的文件，返回禁止缓存的响应。

研判建议节点分别生成面向顾问的跟进建议和面向客户的沟通话术。跟进建议说明顾问应核实的信息、补充资料和推进步骤，沟通话术使用顾问可直接对客户说的称呼和口吻。后端按这两个独立段落写入 recommendation 和 talk_track，兼容旧工作流的文本分段。

## 学生服务事项与学籍展示

学生通知保留原字段，并按当前学生身份批量读取关联请假、反馈或考务，增加摘要与详情；关联源缺失或不属于本人时不返回源内容。GET /api/v1/student/academic-profile 返回关联学生的学籍姓名、学号、当前项目和班级、学校、专业、留学地区和有效班主任，仅使用官网学生身份，不依赖CRM客户关联。原/profile响应保持不变。学生/website/profile显示只读学籍，游客仍使用原客户资料页面。学生服务采用导航与内容独立滚动，欢迎首页展示近期考务，其余业务页保留定时刷新的考务提示，助手采用独立对话布局。

学生位置问答明确区分学籍去向和当前所在地，不根据历史助手回复猜测学校或位置；医院相关咨询先走资料/澄清，不直接推定请假。学生Dify兜底提示同时限制无依据身份、代办承诺和记忆重复计数。


## 学生服务：交流、引导与公开生活知识（本地交流知识版）

STU_ASSISTANT_MODE=workspace时，assistant_workspace负责编排；assistant_guidance输出逐步引导并约束明确办理意图；assistant_tasks保留带版本的确认事务。普通抱怨和想家通过自然交流分支，不自动创建请假或反馈。高风险处置继续调用原安全路径；独立自评与关怀模块未变更。

assistant_knowledge与student.repository提供按国家过滤的已核对公开FAQ。Dify通过受STU_KNOWLEDGE_TOKEN保护的/api/v1/student/knowledge/retrieval读取，不传官网学生Bearer或访问学生私有数据。Dify中德国、新加坡各绑定一个外部知识库，使用同一检索服务、不同knowledge_id。当前为关键词/问题片段排序，未引入向量模型。检索得到的知识编号经后端在本国候选记录中复核，最终关键事实来自已核对FAQ。

028迁移添加overseas_life_knowledge.details JSON（步骤、FAQ、公开联系方式及多来源）与stu_assistant_message.presentation_json JSON（卡片与选择项）。办理表单由后端guide提供，客户端输入仍走既有身份和事务校验；对话展示元数据只由服务器生成，不作为下轮办理授权。新增路由仍归属已注册student.router，无自动建表。

前端StudentHome为默认欢迎页；StudentLife按浏览国家展示同一资料，可切换国家，不修改学籍；StudentAssistantGuide呈现步骤与确认。全部源码共用，两个国家分别验证。生成图片是场景示意，不代表实际合作院校、医院或服务地点。

学生/api/v1/student/complaints保持路径与本人权限，列表扩展为本人投诉与建议，响应增加ticket_type供界面区分；不包含咨询记录，不改变员工可见范围。对应隔离测试覆盖建议不丢失及其他学生不可见。

员工日报周报详情展示已提交的报告原文。员工周报详情提供按该员工本周原文生成 AI 总结的操作。单人总结 POST /api/v1/reporting/board/employees/{employee_id}/summary 复用正式报告 Dify 工作流，要求 reports:summary:read 与 reports:formal:generate，并按所选员工和日期范围读取已提交正文。等待模型期间释放数据库事务，返回前再次核对授权和原文版本。

智报中心各模块的历史报告读取 report_generation 归档记录。GET /api/v1/reporting/archive 可选按 kind 筛选并指定 limit，沿用 before_id 和账号、组织、班级的归档授权。各模块每页显示五条，计划与归档页汇集账号可访问的类型。

analysis 与 analysis_repository 承担新增报表分析。客户经营 analysis 接口提供新增客户同环比及国家、学历、项目、渠道特征分群，签约比例采用同批客户当前状态。投诉 analysis 接口从 ticket_processed 审计读取首次 processing 与 resolved 的时间，统一 UTC 审计与北京时间业务记录后计算耗时，无历史审计的工单不推断耗时。wellbeing/trend 提供当前授权学生范围的近八周统计。心理周报 AI 输入扩展至预警交叉统计、情绪标签、分值及预警原因，模型返回前按全部输入字段复核版本。

030_report_analysis_rules.sql 增加报表规则、定时 AI 选项和自评提醒去重表，由 analysis_models 注册。规则留空时相应判定停用，管理员使用 users:manage 配置并通过版本号防止覆盖更新。高价值候选采用已有研判匹配度阈值；项目健康度按未解决投诉、过期申请和过期考务涉及学生比例及配置权重计算。客户 K-means 以年龄、匹配度、未联系天数为标准化特征，缺失有效特征的客户单独计数；不推断未记录的状态路径。

归档 shared 查询为新增可选范围，经营与员工报告依生成者组织归属、保存时的成员快照再次核验，心理报告依当前班级学生集合核验。PDF 下载使用同一 shared 范围。定时计划 include_ai 可选生成正式员工报告或汇总摘要；未设置选项的旧计划继续采用统计快照。扫描器持有计划行锁直到归档及 last_run_time 同一事务提交，AI 失败回滚后重试。

rule_signals 按管理员配置发送客户跟进、投诉超时和升级提醒，按收件人、事项、规则版本与重复周期去重。学生自评在原有授权及同日记录锁内检查连续条件，自评提示须人工核验；同一连续区间同一规则版本仅建一次预警。关怀建议仅生成草稿，依据个案说明及最近十条跟进，由原跟进入口人工确认后保存。投诉 AI 分类也通过原分类分派入口人工核验，提交时仍检查原状态与分派版本。

增强 AI 使用独立的 docs/dify/report-analysis.yml 工作流，配置 DIFY_REPORTING_ANALYSIS_API_KEY。原员工正式报告继续使用原工作流密钥。工作流返回固定四段式结构，分类场景仅在 work_summary 返回 learning 或 company，其余字段须为非空字符串。新增本地配置密钥存于已忽略的运行配置文件，仓库不保存密钥。本地已应用 030 迁移并启动扫描器；其他环境须先应用迁移并配置增强工作流。

心理健康周报按当前学生归属授权。经理使用 029 迁移授予的 reports:wellbeing:read 查看全体正常状态学生的群体汇总。班主任的周报范围来自当前班级名册，自评汇总仍要求有效授权并遵守最小样本门槛。班主任的草稿、定时生成、归档和 PDF 下载按同一班级范围核对。个人预警和关怀个案沿用各自的权限。

心理周报分布图在 wellbeing_repository 读取所选周 student_psych_record 的 emotion_tag、emotion_score 和 student_psych_alert 的 trigger_reason。心理记录沿用有效自评授权与每组五名不同学生的展示门槛，数量按记录条数统计。分值使用二十分区间及未评分、无效分值分组。预警原因按关键词优先归入学习压力、生活适应、人际关系、情绪困扰和其他原因，返回分类计数。风险等级和当前处理状态由本周新增预警的交叉统计汇总。

客服推荐与 `/api/cs/catalog/recommendations` 共用公开目录。带学历的项目查询将大专与专科等别名统一，匹配已上架项目的目标人群或已发布官网卡片中对应招生对象的路径段落。按国家退回的候选仅返回项目名称等身份信息，不返回无法匹配学历的摘要或人群。031 在默认新加坡卡片附加已记载的初中及专升本路径介绍。德语、英语和语言课程的简短问法（如「德语课」）沿用课程目录查找和已有关联会话纠偏。


### 学生助手交互与本地记忆管理（2026-11-17）

学生workspace增加规划/核实/可见回复三个阶段；Dify同应用22节点，流式Answer直接接可见LLM，完整句经assistant_reply_stream验证后才向SSE累计text事件发布。知识正文只能沿用后端已核实内容；事务办理、确认、本人事实卡与高风险处理由后端保留。失败保留已经核验的可见前缀，并给出真实的中断提示；不再次执行办理。

新增memory_repository/memory_service，提供本人长期记忆分页、纠正、删除和清空。管理请求校验当前账号与内容版本；所有写入先锁本人sys_user行再操作记忆。内部epoch控制记录使用既有stu_mem0_memory.metadata_json，并从列表、检索及按ID修改/删除中排除；管理操作推进epoch，阻止此前在途回答重新写回已删记忆。删除长期记忆保留聊天原文。当前仅管理本地存储，外部Mem0已配置时拒绝声称已删除远端数据的本地管理操作。新记忆只摘取明确称呼/偏好等学生自述，不再把助手回复写成事实，旧摘要在召回时移除助手段落。

新增PATCH /api/v1/student/assistant/tasks/{id}/attachment，验证上传证明属于本人并持久化到未结束草稿，递增版本使旧确认失效；确认仍使用同一业务事务。任务返回ordinal/updated_at供前端拒绝迟到旧状态。建议与投诉办结均产生去重站内结果通知。知识目录来源迁移只接受显式previous_source_url，其他同名异源记录继续拒绝。无需新增数据库DDL。


### 学生助手当前答复路线（v5，2026-11-17）

公开知识由assistant_knowledge对原问及可靠用户上文解析主题/对象/国家，直接组织已审核短答；完整FAQ保留按需展开。普通交流只进行一次只读Dify可见生成，业务字段提取仅在需要时进行一次有总预算的规划调用。本人事实和正式提交仍由原服务/草稿状态机处理。模型调用使用首正文和总墙钟截止，不依赖心跳读取间隔超时；非学生模块默认调用保持兼容。公开知识来源以facts_kind区分于完整业务事实卡，并随presentation保存。详见docs/student-workspace/response-flow-v5.md。

### 学生助手与最新整合版兼容（2026-11-17）

本轮基于0a1a7ad保留权限、智报、老师预警汇总及官网项目路径更新，接入本地学生模块改进。学生会话按已认证账号和本人conversation_id读取近期20条带角色上下文，官方记录、自述记忆和当前安全自述分开提供。安全表达先给简短核验提醒，模型仅续写；整轮生成预算15秒，首内容预算不超过12秒。当前新危险沿原预警写入服务执行一次，后续解释不重复写预警、不入长期记忆；旧入口generate_reply默认True兼容，新workspace关闭旧同步回复以避免重复模型等待。

学生记录写入与上游alerts.weekly_alert_totals、老师处理、经理按授权读取聚合继续使用原表结构；新增报表分析表及经理授权须按029/030迁移部署，031保留默认官网卡片条件更新。共享数据库迁移不由应用启动自动执行。Dify学生应用继续使用既有22节点图，增强报表工作流仍使用独立DIFY_REPORTING_ANALYSIS_API_KEY，不能混用学生应用密钥。


学生工作台的 `assistant_personal` 只从当前账号上下文选择问题所需字段，`assistant_grounding` 为只读自然生成检查具体事实边界；业务事务、账号范围与草稿确认仍由原服务负责。本人单字段问答、检索知识可通过同一个可见回复模型，模型不可读取任意数据库或执行正式业务。

2026-11-18 学生与员工处理闭环：`feedback/access.py` 统一工单、业务待办、站内通知与工作台计数的渠道隔离；公司／人员投诉仅主管和管理员可查，老师即使有错误历史分派也不能读取详情、历史或来源待办。明确投诉班主任的文本在草稿与提交时交主管；旧学习类误分类文本在老师查询时保密。主管渠道不能向班主任降级改派，投诉和建议均支持主管修复分派。员工 AI 保存工单编号并在读取历史时重新核验当前可见范围；缺少来源编号的旧成功结果要求重新查询，业务结果不进入模型闲聊历史。处理权限仍要求当前负责人，列表返回只读 can_process；状态按预期值原子更新。

请假新增本人审批记录及审计历史接口，证明附件按指定审批人和 leave 类型检查，拒绝须提供不超过512字的意见；编号审批、姓名指令与企业助手均遵守该规则。审批结果、学生通知、来源待办和审计同事务提交，重复处理返回冲突。来源请假／工单待办禁止手动完成或取消，按原单自动同步；扫描会恢复历史上被提前完成的未结事项。学生记录每30秒更新。正式单据仍须由学生确认草稿后产生，不新增数据库结构。

本机测试官网可配置忽略跟踪的 frontend/.env.local：VITE_STUDENT_TEST_USERNAME、VITE_STUDENT_TEST_PASSWORD，仅开发模式且环回地址显示填充按钮，仍走正常登录；生产包已检查不含测试凭据。主管类反馈需配置 COMPANY_COMPLAINT_MANAGER_ID 为有效且具备工单读写权限的主管，多候选时不自动选择。本机联调已指向已有主管账号，其他环境自行配置。
