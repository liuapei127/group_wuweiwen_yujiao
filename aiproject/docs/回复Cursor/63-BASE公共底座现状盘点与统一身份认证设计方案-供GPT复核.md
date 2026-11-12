# 63 BASE 公共底座现状盘点与统一身份认证设计方案（供 GPT 复核）

日期：2026-11-12  
范围：对照原始资料和全系统文档，盘点 BASE-01～05 以及后加的统一身份。只审查和设计，不改认证、数据库、业务代码、生产配置，也不发布工作流。  
密钥只记录变量名和文件位置，不记录内容。

本轮没有找到文件名或正文标题为「11 月 10 日组会会议记录」的文档。能核对到的会议记录是 `docs/组会纪要-2026-11-11.md`（2026-11-11 20:10—21:50）。更早的任务卡原文在 `教育服务_0914/1111组长前期看怎么规划任务/开发引导new.md`。

## 第一章：BASE 原始需求

`教育服务_0914/0000最原始的需求内容.rar` 已解压。里面是客户业务材料：客户需求表、公司信息、留学政策、用户研判规则。这些材料没有 BASE-01～05 的工程编号，也没有统一 JWT 契约。BASE 五张任务卡来自开发引导，产品说明书再抄了一次，并追加了统一身份。

| 编号 | 原始表述 | 来源与位置 | 边界 |
| --- | --- | --- | --- |
| BASE-01 | 项目骨架初始化：FastAPI 工程、requirements、`/health`、目录分层 | `开发引导new.md` 第 4.3 节，约第 311 行。产品说明书第 3.1 节第 90 行写成「工程骨架、Swagger、/health」 | 一个 FastAPI 进程。不包含五个业务模块的功能 |
| BASE-02 | Git 仓库、`.gitignore`、分支保护、提交规范 | 开发引导第 312 行，细则在第 7 部分（约第 581 行起）：`main`/`develop` 不直接写，`feature/<模块>-<任务卡>`，合并请求进入 | 规范落地，不是业务功能 |
| BASE-03 | 跑通 `db_init.sql`、配置连接、验证一次增删改查 | 开发引导第 313 行，依赖 BASE-01。脚本在 `教育服务_0914/2222通过表可以实现curd/db_init.sql`，共 31 张 `CREATE TABLE` | 连通和 31 表，不要求本卡做完全部业务 CRUD |
| BASE-04 | Dify 应用/工作流命名规范、API Key 管理 | 开发引导第 314 行。产品说明书第 93 行指向本地 Dify | 环境、命名和密钥管理。不包含某一条业务 Chatflow 的节点设计 |
| BASE-05 | 确定本地或云演示方式，保证随时能演示 | 开发引导第 315 行，依赖 BASE-01。产品说明书指向 `backend/docs/腾讯云部署与小组协作.md` | 演示环境，不是功能验收本身 |
| 增项 | 统一员工身份 JWT | **不在**开发引导的五张 BASE 卡里。产品说明书第 3.1 节第 95 行标为「（增）」。组会纪要第 59、38 行写明未合入、阻塞业务 API。`04-认证阻塞项与契约待决.md` 列出待确认项 | 公共身份。各模块仍做自己的业务授权 |

产品说明书第 72～80 行把 BASE 目录写成 `main`、health、DB、auth、files，服务对象是全员，负责人建议是组长加集成。五个业务模块共用这一个进程。

## 第二章：当前代码实现情况

当前可运行的后端是 `aiproject`。`backend/` 是另一套更早的 FastAPI，有 health、CRM、课程和请假路由，没有 JWT。它不是 `aiproject/app/main.py`。两套不要当成同一个已上线服务。

| 需求 | 实际位置 | 现状 |
| --- | --- | --- |
| BASE-01 | `aiproject/app/main.py`、`app/router_registry.py`、`app/modules/system/router.py`、`aiproject/pyproject` 或 requirements 所在工程、FastAPI 默认 `/docs` | 单进程已挂上 system、auth、portal、assistant 和 ENT 各路由。`GET /health` 返回 `{"status":"ok"}`，不查库。`GET /health/db` 用 `ping_database()`。62 号已验证本机 8000 的 `/health` 为 200。Swagger 使用框架默认地址，没有单独的分组规范 |
| BASE-02 | 仓库根 `.gitignore`、`aiproject/.gitignore`；远程 `origin` 为 `http://47.106.207.27:3000/0914/group_wuweiwen_yujiao.git` | 本地 `main` 只有 `177df8f Initial commit`。`aiproject/`、`backend/`、`docs/` 仍未纳入版本库。本次 `git fetch` 认证失败，看不到远程新提交，也没有分支保护证据。开发引导第 7 部分的 `develop` 和 `feature/` 流程没有落地 |
| BASE-03 | `db_init.sql` 31 张表；`aiproject/app/core/database.py`；`app/core/config` 的 `DB_HOST`、`DB_PORT`、`DB_NAME`、`DB_USER`、`DB_PASSWORD` | ORM 已连接。业务代码直接用 SQLAlchemy。没有 Alembic。ENT 新增表写在 `migrations/001_ent_reliability_expected.sql` 和 `migrations/002_ent_portal_expected.sql`，由门户初始化脚本执行，不是全组统一迁移器。31 张原始表仍然是基线 |
| BASE-04 | 配置名 `DIFY_API_URL`、`DIFY_WORKFLOW_API_KEY`、`DIFY_TIMEOUT_SECONDS`，定义在 `app/core/config/__init__.py`，值在 `aiproject/.env`（已被 gitignore） | 本机 Dify 容器此前在 8088 运行。密钥没有写进报告。没有全组应用命名注册表，也没有密钥轮换实现。ENT 已发布工作流是业务成果，不属于 BASE-04 的完成证明 |
| BASE-05 | `aiproject/compose.api.yaml`、`aiproject/compose.network.yaml`；说明在 `backend/docs/腾讯云部署与小组协作.md` | compose 把 API 绑到 `127.0.0.1:8000`，并接入外部网络别名 `education-api`。组会纪要仍写云上业务 API 未作为入口开放。本机 8000/8002 是开发进程，不是 BASE-05 已验收的演示环境 |
| 统一身份增项 | 见第三章 | 只有 ENT 门户这一套实现。8000 默认 `blocked`。没有全组签发方、JWKS 和模块接入契约 |

`app/modules/files`、`student`、`offer`、`statistics` 只有占位说明，没有路由。产品说明书里的 files、PF、CS、STU、RPT 目录大多还没实现。

## 第三章：统一身份认证现状

员工和学生都在原始表 `sys_user`。`db_init.sql` 第 32～49 行：`id` 自增，`user_type` 为 `student`、`employee`、`admin`，`status` 为 `normal` 或 `disabled`，`role_id` 指向 `sys_role`，`department` 是字符串，不是组织表外键。密码列是 `password_hash`。

组织表 `sys_organization`（第 53～66 行）有 `parent_id`、`org_level`、`manager_id`。没有「员工属于哪个组织节点」的成员表。员工部门以及主管关系因此没有被身份令牌表达出来。

ENT 在这套表之外加了五张认证表，定义见 `app/modules/auth/models.py` 和 `migrations/002_ent_portal_expected.sql`：

- `ent_auth_role_permission`：角色到权限码。
- `ent_auth_student_scope`：员工可操作哪些学生。
- `ent_auth_session`：会话，含 `expires_at`、`revoked_at`。
- `ent_auth_login_attempt`：失败计数。
- `ent_auth_audit`：登录和账号变更审计。

权限码目录在 `app/core/security/rbac.py`，内容是 ENT 工作台的客户、日报、成绩、请假、工单、待办和 AI。`student` 角色的默认权限是空集。登录服务拒绝 `user_type` 不是 `employee` 或 `admin` 的账号，也拒绝把 `student` 角色分配给员工。

### 对照表

| 功能 | 当前代码位置 | 当前实现 | 是否可复用 | 缺少什么 |
| --- | --- | --- | --- | --- |
| 员工登录 | `app/modules/auth/router.py` `POST /api/v1/auth/login`；`AuthService.login` | 校验密码、账号 `normal`、角色启用、用户类型为员工或管理员。失败统一 401。同一账号加来源 15 分钟 10 次失败后 429。成功写会话和审计 | 是，可作为全组员工登录的基础 | 学生入口；全组签发方；8000 默认仍不启用它 |
| JWT 签发 | `app/core/security/credentials.py` `issue_token` | HS256。claims：`sub`、`sid`、`iat`、`nbf`、`exp`、`iss`、`aud`、`typ=access`。默认 `iss=ent-portal`，`aud=ent-api`，有效期 `AUTH_ACCESS_MINUTES`，默认 60，范围 5～1440 | 签发流程可复用 | 这不是 BASE 签发方。没有 `user_type`、角色、组织 claim。没有公钥 |
| JWT 验证 | `decode_token`；`require_employee`；`AuthService.authenticate` | 先验签名、签发方、接收方和必填 claim，再查会话未撤销、账号仍有效，然后装入 `EmployeePrincipal` | 验证步骤可复用 | 只认当前这一个 HMAC 密钥。无 JWKS，无轮换。PF/CS/STU/RPT 没有自己的验签实现，也还没接到这里 |
| 角色管理 | `sys_role`；`/api/v1/auth/roles`；`ent_auth_role_permission` | 可增改角色并保存权限码。权限码是 ENT 目录 | 角色表可复用 | 权限码不能直接当成五模块的公共权限。没有组内确认的角色清单 |
| 组织管理 | `sys_organization`；`GET /api/v1/enterprise/organizations` 等 | 按关键字查组织、同事和联系方式。联系方式另要 `directory:contacts` | 表和查询可作目录 | 员工 `department` 不指向组织节点。令牌里没有部门或主管。不能据此做跨部门隔离 |
| Token 刷新 | 无 | 只有 access token | 否 | 没有 refresh 接口、刷新令牌存储和轮换 |
| Token 撤销 | `ent_auth_session.revoked_at`；登出、改密、重置密码、停用账号都会撤销 | 验签之后还检查会话。停用账号后旧令牌不能再通过 `authenticate` | 会话表可复用 | 只对会调用这套 `authenticate` 的进程有效。没有全组吊销列表或密钥作废流程 |
| 审计日志 | `ent_auth_audit`；`GET /api/v1/auth/audit` | 记录登录、登出、改密、建号、改号、重置和学生范围。失败登录进 `ent_auth_login_attempt`，不进审计表 | 是 | 没有覆盖其他模块的业务操作。审计权限码 `audit:read` 仍是 ENT 目录里的一项 |

密码使用 `pwdlib.PasswordHash.recommended()`，比较失败时用固定假哈希降低时序差异。明文密码不入库。

8000 的 `EMPLOYEE_IDENTITY_MODE` 在 `.env` 中是 `blocked`。`require_employee` 在模式不是 `trusted_jwt` 时直接 503，不读取令牌。8002 由 `scripts/start_ent_portal.py` 单独设为 `trusted_jwt`。两套进程密钥变量同名，但是否加载取决于各自进程环境。不能把 8002 的通过记录写成 8000 已接入 BASE。

测试：`tests/integration/test_ent_portal_routes.py` 覆盖状态形状、blocked 返回 503、trusted_jwt 无令牌返回 401、非法 JWT 返回 401。`tests/integration/test_ent_access_boundaries.py` 保持生产入口默认拒绝。这些测试用隔离库，不代替五模块联调。62 号记录的全量 pytest 是 115 passed；本轮没有重跑，也没有改这些测试。

## 第四章：现有系统的问题

**重复**

- `backend/` 与 `aiproject/` 各有一个 FastAPI。旧后端没有身份检查，若被单独启动，会和 8000 的默认拒绝形成两套入口。
- ENT 门户登录已经实现了账号、角色、会话和审计，但命名和权限目录都是 `ent-portal` / ENT 功能码。若再新建一套平行用户表，就会把 `sys_user` 拆成两份。

**缺失**

- 五张 BASE 卡里，BASE-02 和 BASE-05 没有验收证据。files、PF、CS、STU、RPT 的业务路由基本还是空包。
- 没有学生登录。学生账号存在 `sys_user.user_type=student`，当前登录直接拒绝。
- 没有刷新令牌、JWKS、密钥轮换和跨模块权限命名空间。
- `department` 与 `sys_organization` 没有外键。主管只写在组织节点的 `manager_id`，没有成员关系。

**安全风险**

- 全组若继续用一把 HS256 密钥，每个要验签的模块都必须持有签发密钥。密钥一处分发，就等于处处都能签发。
- 8000 保持 blocked 是当前正确边界。若为了让公开 Dify 写库而改成 trusted_jwt，又没有 BASE 验签，就会把 ENT 门户密钥或伪造员工号暴露到公共链路。
- 旧的 `AUTH_BEARER_TOKEN` 仍在配置类里，注释写明它只是服务间令牌，不是员工身份。04 号已记录历史上用它加 `X-Employee-Id` 可以冒充员工。生产 `app.main` 不接受 `insecure_header_repro`。这套复现代码只能留在 `tests/repro`，不能当 BASE 方案。
- 模型、对话变量和客户端头都不能作为员工编号来源。62 号已验证伪造头和伪造 Bearer 在 blocked 的 8000 上仍是 503，且没有新增业务行。

## 第五章：BASE 目标架构

下面是依据现有表和代码提出的方案，不是已经确认的组内标准。issuer、audience、算法和 claim 名称要等组内确认后才能写进生产配置。

**身份服务**  
继续使用 `sys_user`。员工 ID 就是 `sys_user.id`。`user_type` 区分 `employee`、`admin`、`student`。停用仍写 `status=disabled`，并撤销该用户全部分话。

**登录**  
员工继续走现有 `POST /api/v1/auth/login` 的校验、限流和审计。学生不走这条接口。学生入口单独设计，成功令牌的 `user_type` 必须是 `student`，并且不能携带员工权限码。确认前不新增学生登录。

**签发**  
建议 BASE 使用非对称签名，业务模块只拿公钥或 JWKS 验证。现有 HS256 和 `ent-portal` / `ent-api` 继续只服务 8002 过渡期。建议中的全组签发方、接收方不要沿用这两个值；具体字符串待确认。access token 建议保留现有 60 分钟上限，并增加一次性刷新令牌。claims 建议在现有 `sub`、`sid`、`iat`、`nbf`、`exp`、`iss`、`aud`、`typ` 上增加 `user_type`。角色编码可以进令牌，组织范围在成员关系做好之前不要假装已经进令牌。

**验证**  
抽一个公共依赖：先验签和 claim，再按 `sid` 查 `ent_auth_session`，再按 `user_type` 分流。员工请求装入员工主体，学生请求装入学生主体。8000 在这套验证可用之前保持 `blocked`。各模块不保存第二套用户表，也不各自保存签发私钥。

**角色与组织**  
`sys_role` 继续做角色字典。ENT 的 `ent_auth_role_permission` 先视为 ENT 权限，不自动授权 PF、CS、STU、RPT。公共层只保证「这个人是谁、是员工还是学生、角色编码是什么」。客户是否可见、报告是否可看，仍由各模块用自己的规则判断。组织要先有成员关系，才能把「销售部主管」放进身份；在此之前，ENT 继续用 `require_owned` 和 `require_student_scope` 做数据范围。

**刷新、撤销、密钥**  
刷新令牌单独存储、使用后轮换，撤销时与 access 会话一起失效。登出、改密、停用沿用现有 `revoke`。密钥材料只放环境变量或后续的密钥文件，不进仓库、不进 Dify 提示词。轮换时保留上一把公钥一个过渡窗口，只用于验证，不用于签发。泄露时作废 `kid`、撤销全部会话，并要求重新登录。

**模块接入**  
Dify 模型不接收 JWT。公开工作流要等有「模型改不了」的凭据位置后，才把员工或学生令牌传给 API。没有这个位置之前，不改 8000 的默认拒绝，也不发布新的公开工作流。

## 第六章：数据库设计建议

本轮不执行这些变更。

**复用**

- `sys_user`、`sys_role`、`sys_organization`。
- `ent_auth_session`、`ent_auth_audit`、`ent_auth_login_attempt`。名称带 `ent_`，因为它们已经在用；迁移时可以保留表名，避免推倒 ENT 会话。
- `ent_auth_role_permission`、`ent_auth_student_scope` 继续服务于 ENT，不扩展成五模块的总权限表。

**建议新增，确认后再做**

- 组织成员：`user_id`、`org_id`、是否主部门。用来替换仅靠 `sys_user.department` 字符串的做法。
- 刷新令牌表：哈希、所属会话、过期时间、轮换后的替代记录。不存明文令牌。
- 若五模块都要公共权限码，另建带模块前缀的授权表。不要把 `crm:write` 写进 PF 或 RPT。

关系保持为：用户属于一个角色；用户通过成员表属于组织；组织用 `parent_id` 形成树，`manager_id` 指向 `sys_user`。学生业务表继续用 `student_info` 和现有学生业务表，不把学生行改造成员工行。

## 第七章：五大业务模块接入方案

| 模块 | 需要 BASE 提供什么 | 当前代码 | 接入方式 |
| --- | --- | --- | --- |
| PF | 上传和研判的员工身份；操作人写入审计 | 无 `modules/profile` 路由。表 `profile_rule`、`customer_source`、`customer_profile` 已在 31 表中 | 先接员工令牌。研判结果是否可见由 PF 定。不把 ENT 的 `crm:write` 当成研判权限 |
| CS | 后台管理用员工身份。访客问答和报名不是员工 | `modules/offer` 只有占位。课程和报名表已存在。旧 `backend/` 有课程路由但无身份 | 访客链路单独定，不发员工 JWT。后台管理才验员工令牌 |
| ENT | 员工身份、角色、以后的组织关系；业务权限仍由 ENT 判断 | 8002 已有登录、四种员工角色验收、门户 AI 写入。8000 仍 blocked。客户范围用负责人字段，学生范围用 `ent_auth_student_scope` | 保留 8002 和现有令牌。BASE 验签完成后，8002 改为消费同一身份服务，而不是删掉登录页面和 RBAC。8000 在验签完成前维持 503 |
| STU | 学生身份与员工身份分开 | `modules/student` 只有占位。请假等员工侧处理在 `student_admin`，入口仍是员工 `require_employee` | 学生令牌不能调用员工审批。员工审批继续看请假是否分配给该员工 |
| RPT | 报告读取者的员工身份和组织范围 | `modules/statistics` 只有占位。表 `report_generation`、`report_schedule` 已存在 | 先有员工令牌。部门汇总要等组织成员关系，不能用客户端传入的部门名 |

迁移顺序：先让公共验签能识别现有 `ent-portal` 令牌和未来的 BASE 令牌；8002 保持可用；学生入口单独做；最后才考虑让公开 Dify 携带令牌。每一步都不删除 ENT 已发布工作流、测试数据和 8000 的默认拒绝。

## 第八章：开发任务拆解

这些任务等 63 号复核通过后再做。本轮没有改文件。

| 任务 | 目标 | 预计修改 | 前置 | 验收 | 测试 | 风险 |
| --- | --- | --- | --- | --- | --- | --- |
| B1 契约确认 | 写下签发方、接收方、算法、claim、错误码 | 只更新 04 号的「实际确认」列 | 组长或集成负责人 | 确认栏不再是「未确认」 | 对照会议结论，不调用生产接口 | 未确认就编码会把建议当成标准 |
| B2 验签组件 | 公共验签支持过渡期的现有 HS256，并预留公钥验证 | `app/core/security/credentials.py`、`dependencies.py` | B1 | 旧门户令牌仍可登录；错误令牌 401；8000 仍可配置为 blocked | 扩展现有 portal 隔离测试，不写 MySQL 业务表 | 改坏 8002 登录 |
| B3 令牌生命周期 | 刷新、撤销和停用后拒绝 | auth service、一张新表的迁移脚本 | B2 | 刷新后旧刷新令牌失效；停用账号后 access 被拒绝 | 隔离库测试 | 与现有会话表重复 |
| B4 组织成员 | 员工挂到组织节点 | 新成员表和只读查询，先不改 ENT 客户授权 | B1 | 能查询某员工的主部门及主管 | 隔离库；不重置 `education_service` | 把字符串部门误迁 |
| B5 学生入口 | 学生登录与员工登录分流 | 新的学生登录路径，不改员工 `login` 的拒绝条件 | B2 | 学生令牌不能进员工接口；员工令牌不能冒充学生 | 隔离库 | 两套身份共用一个权限判断 |
| B6 模块接入 | PF、CS、RPT、STU 在各自路由上声明需要员工还是学生 | 各模块尚不存在的路由，接入时再加 | B2，以及该模块自己的业务卡 | 无令牌被拒绝；有令牌仍走该模块自己的数据范围 | 各模块最小测试 | 用 ENT 权限码代替他模块授权 |
| B7 公开 Dify | 模型不可改的凭据通道 | 不在契约前改工作流 | B1、B2，以及 Dify 凭据位置 | 8000 对无身份请求仍 503；不把令牌放进提示词 | 先做连通和 503，再做一条真实写入 | 为了写库关闭 blocked |
| B8 工程收口 | BASE-02、BASE-05 的证据 | Git 分支说明、compose 启动记录 | 仓库认证可用 | 分支策略有文档；演示环境有一次可重复的启动记录 | 只读检查和 health | 把未跟踪的 `aiproject` 整目录误提交，或提交 `.env` |

## 第九章：最终待办清单

**已完成并有证据**

- BASE-01 的进程、`/health` 和路由注册存在。62 号记录本机 8000 `/health` 为 200。
- BASE-03 的 31 张表脚本和 ORM 连接存在。组会纪要写明云库已导入；本轮没有重连云库复核。
- ENT 门户登录、RBAC、会话撤销和审计已有代码和隔离测试。四种角色 HTTP、Playwright 和 AI 写入证据在 61 号。8000 blocked 的 503 与「不写业务行」证据在 62 号。R7 当前实现和 115 passed 的记录在 61、62 号。本轮没有重跑。

**代码已经存在但未充分测试**

- 组织查询接口只做目录，没有跨部门测试。
- 账号停用撤销会话有代码，本轮没有对真实 MySQL 做停用演练。
- compose 文件存在，本轮没有执行云上构建。

**需要修改**

- 把现有签发方从「ENT 门户专用」设计成可过渡到全组验证，而不是把 `ent-portal` 改名为 BASE。
- `sys_user.department` 与 `sys_organization` 脱节，需要成员关系后才能做部门权限。
- `backend/` 旧入口没有身份，后续要标明废弃或加上同等拒绝，避免双入口。本轮不删代码。

**尚未开发**

- 全组 JWKS 或公钥验证、刷新令牌、密钥轮换。
- 学生统一登录。
- PF、CS、STU、RPT 的业务路由和它们自己的授权。
- files/MinIO。
- 公开 Dify 上模型不可伪造的身份传递。

**等待其他模块提供资料**

- PF：上传人是谁、研判结果谁能看。
- CS：访客与后台管理员的边界。
- STU：学生登录账号是否就是 `sys_user` 中 `user_type=student` 的行。
- RPT：报告按部门汇总时主管范围怎么定。
- Dify：HTTP 节点放置令牌的位置，以及该位置是否对模型不可见。

**需要组内确认**

- 04 号全部「实际确认」栏：签发方、接收方、算法、claim、停用员工返回 401 还是 403、网关还是直连、撤销策略。
- BASE-02 的远程仓库、分支保护和谁可以合并。本次拉取因 `Failed to authenticate user` 失败。
- BASE-05 的演示环境以本机 compose 为准，还是以腾讯云为准。
- 统一身份的负责人。产品说明书建议是组长加集成；ENT 侧由刘培阳实现接入，但不能单方宣布契约已生效。

本轮没有修改业务代码、认证逻辑、数据库、生产配置和已发布工作流。
