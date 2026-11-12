# 64 BASE 统一身份认证架构深化与分阶段开发计划（GPT 最终复核版）

日期：2026-11-12  
保留文件：`64-BASE统一身份认证架构深化与分阶段开发计划-供GPT复核.md`，以及 `64-BASE统一身份认证架构深化与分阶段开发计划-GPT复核修订版.md`。本文件不覆盖它们。若三份表述冲突，以本文件为准。  
本轮只做设计，不改业务代码、数据库、认证逻辑、生产配置和已发布 Dify 工作流。

上一版已确认的方向继续有效：BASE 由刘培阳负责；五张原始任务卡与统一身份分开验收；复用 `sys_user`、`sys_role`、`sys_organization` 和现有登录、哈希、会话、审计；不把 `ent-portal` 改名为 BASE；新令牌用 RS256；员工、管理员、学生、访客、服务分开；8000 在验收完成前保持 `blocked`；8002 的登录、RBAC 和门户 AI 写入保留。

本机 `education_service` 的数据库版本已核对为 **MySQL 8.0.27**（`SELECT VERSION()`，与 `45-本地数据库与ENT测试数据使用说明.md` 一致）。下面的组织表按这个版本设计。

## 1. 完整统一身份架构

一个 `aiproject` 进程提供身份。业务模块只拿到公钥，并在验签之后读取会话。签名成功不等于授权完成。

每个受保护请求的顺序是：按入口选择验签器 → 固定算法验签 → 核对 `iss`、`aud`、`token_use` → 按 `sid` 查对应会话表 → 再读数据库中的账号状态、账号类和权限 → 进入该模块原来的 service。会话库不可用则返回 503。

| 身份 | 账号存放 | 令牌 | 会话 |
| --- | --- | --- | --- |
| 员工 `employee` | `sys_user` | `token_use=access`，`sub` 为数字 id | `ent_auth_session` |
| 管理员账号类 `admin` | `sys_user.user_type=admin` | 同上，仍走员工主体通道 | 同上 |
| 学生 `student` | `sys_user`，生命周期未确认前不开放登录 | 设计为 `aud=edu-api:stu` | 将来仍用 `ent_auth_session`，现在不签发 |
| 访客 `guest` | 无账号 | 不签发 | 无 |
| 服务 `service` | `auth_service_client`，不是 `sys_user` | `token_use=service_access`，`sub=svc:<client_id>` | `auth_service_session` |

`user_type=admin` 只表示管理员账号类。它和“员工行加上 `role_code=admin`”不是同一种数据。两者都进入员工主体通道。权限来自角色权限表，不来自 `user_type`。管理员不能仅凭账号类跳过客户归属或其他业务范围。

角色、权限和组织范围不写入 JWT。每次请求从数据库读取，所以权限变更下一次请求就生效。

## 2. BASE-01～05 原始任务验收矩阵

统一身份不改变这五张卡的口径。

| 卡 | 原始验收 | 当前判断 | 不能当成完成的东西 |
| --- | --- | --- | --- |
| BASE-01 | 工程可启动，`/health`、`/docs` 可用 | 本地进程和健康检查已有 | JWKS、登录、8000 业务开放 |
| BASE-02 | 仓库、分支、提交，且密钥不入库 | 尚未完成。未审清单前禁止整目录 `git add` | 一次成功的 `git status` |
| BASE-03 | 31 张表、连接、一次 CRUD | 脚本和连接已有。没有 Alembic 不算失败 | 云库本轮没有重做 CRUD |
| BASE-04 | Dify 命名、API Key 存放和轮换 | 密钥在被忽略的环境文件中 | 已发布的 ENT 工作流 |
| BASE-05 | 腾讯云上的 `aiproject` 演示环境 | 本地 Compose 只用于预演 | 只有本机 8000 启动成功 |

## 3. 五类身份

全组只用第 1 节的表。不允许模块把 `admin` 解释成服务、学生，或解释成自动拥有全部数据。

学生登录的路径形状可以保留为 `POST /api/v1/auth/student/login`，但在 STU 确认账号由谁创建、初始密码、找回、离校停用、是否已有独立入口、现有学生是否都在 `sys_user` 之前，不实现、不开放。

访客只访问事先列明的公开接口。服务身份见第 8 节，不能因为 JWT 验签通过就调用员工业务。

## 4. RS256 与 JWKS

新令牌 Header：`typ=JWT`，`alg=RS256`，`kid` 为密钥编号。`typ` 不表示 access 或 service。

Payload：

| 字段 | 员工或管理员 access | 服务 `service_access` |
| --- | --- | --- |
| `iss` | `edu-base` | `edu-base` |
| `aud` | 一个资源受众，如 `edu-api:ent` | 策略中允许的一个资源受众 |
| `sub` | `sys_user.id` 的十进制字符串 | `svc:` 加客户端编号 |
| `sid` | `ent_auth_session.id` | `auth_service_session.id` |
| `user_type` | 数据库原值 `employee`、`admin` 或 `student` | 不出现 |
| `token_use` | `access` | `service_access` |
| `iat` / `nbf` / `exp` | access 最长 60 分钟 | 由客户端策略限制，不超过 60 分钟 |

验签器的算法白名单只有 `RS256`。不读取令牌里的 `alg` 来选择 HMAC 或 RSA。`alg=none` 拒绝。

私钥不进 MySQL，也不进仓库。元数据和私钥分开，见第 12 节。JWKS 只发布公钥。

## 5. HS256 过渡隔离

8002 上的门户验签器单独存在，只接受现有组合：算法固定 HS256、`iss=ent-portal`、`aud=ent-api`、payload `typ=access`，密钥仍是 `AUTH_JWT_SECRET`。

8000、PF、CS、STU、RPT 不加载这把 HMAC 密钥，也不调用这个验签器。`ent-api` 不自动等于 `edu-api:ent`。两套验签器不共用“先看 alg 再分支”的函数，避免把公钥当 HMAC 密钥做算法降级。

历史门户会话的 `signing_kid` 保持 NULL。它们只由 8002 的旧验签器认可。

## 6. Refresh Token

刷新令牌是 256 位随机字符串，不是 JWT，没有 `token_use`。数据库表 `auth_refresh_token` 只保存 SHA-256、`family_id`、`session_id`、`user_id`、`expires_at`、`used_at`、`revoked_at`、`replaced_by`。明文不入库。

轮换使用一个事务，并对命中的刷新行 `SELECT … FOR UPDATE`：

1. 找不到哈希：401，不签发。
2. `used_at` 或 `revoked_at` 已有值：撤销该 `family_id` 的全部刷新行和对应 `ent_auth_session`，提交后 401，要求重新登录。
3. 行仍可用：写 `used_at` 和 `replaced_by`，插入同一家族的新哈希，提交后返回新的 access 和新的刷新串。

并发使用同一刷新串时，后获得锁的请求会看到 `used_at`，于是整个家族撤销。客户端必须串行刷新。登出、改密、停用账号和密钥停用，都会撤销相关会话和家族。

N14、N15 在启用刷新之前必须通过。刷新未启用时，不把这两项当作 8000 开放的前置条件。

## 7. 组织数据库约束

MySQL 8.0.27 不允许生成列使用 `NOW()` 或 `CURRENT_TIMESTAMP`，因为它们不是确定性表达式。8.0.27 也没有带 `WHERE` 条件的部分唯一索引。因此不能用“生成列里判断当前是否到期”来保证只有一个主部门。

比较：

| 方案 | 能否在 8.0.27 上执行 | 判断 |
| --- | --- | --- |
| 生成列包含当前时间 | 不能。非常量时间函数不能用于生成列 | 不采用 |
| `is_primary` 加不含时间的生成列唯一索引 | 能保证最多一个主标记，但时间和标记缠在一起 | 能用，但撤销和并发不如单独的一行清楚 |
| 成员表加独立主部门表 | 能。主键天然保证一人一行 | **采用** |

成员关系在 `sys_org_member`。主部门指针在 `sys_user_primary_org`。一人可以有多条成员关系；主部门指针最多一行。授权查询再判断时间窗口。窗口过期时指针可以仍在，但查询结果为空，因此不会出现两个有效主部门，也不会把过期主部门当成授权。

```sql
CREATE TABLE sys_org_member (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  user_id BIGINT UNSIGNED NOT NULL,
  org_id BIGINT UNSIGNED NOT NULL,
  effective_from DATETIME NOT NULL,
  effective_to DATETIME NULL,
  status ENUM('active','inactive') NOT NULL DEFAULT 'active',
  create_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uk_member_id_user (id, user_id),
  UNIQUE KEY uk_user_org (user_id, org_id),
  CONSTRAINT chk_member_window CHECK (effective_to IS NULL OR effective_to > effective_from),
  CONSTRAINT fk_member_user FOREIGN KEY (user_id) REFERENCES sys_user (id),
  CONSTRAINT fk_member_org FOREIGN KEY (org_id) REFERENCES sys_organization (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE sys_user_primary_org (
  user_id BIGINT UNSIGNED NOT NULL,
  member_id BIGINT UNSIGNED NOT NULL,
  update_time DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (user_id),
  UNIQUE KEY uk_primary_member (member_id),
  CONSTRAINT fk_primary_member FOREIGN KEY (member_id, user_id)
    REFERENCES sys_org_member (id, user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

`UNIQUE(user_id, org_id)` 禁止同一员工与同一组织重复建关系。`PRIMARY KEY(user_id)` 禁止两个主部门指针。复合外键禁止把甲的主部门指到乙的成员行。`CHECK` 在 8.0.16 之后会真正生效，本库 8.0.27 满足。执行前要先核对历史脏数据，避免外键建表失败。本轮不执行这段 DDL。

更换主部门的事务：

1. `SELECT … FROM sys_user_primary_org WHERE user_id=? FOR UPDATE`。
2. `SELECT … FROM sys_org_member WHERE id=? AND user_id=? FOR UPDATE`，确认 `status=active` 且窗口当前有效。
3. 没有指针就插入；已有指针就更新 `member_id`。
4. 提交。

两个并发事务会堵在同一个人的主键行上。后提交的更新覆盖同一行，最终仍是一个指针。同时插入时，后一个得到主键冲突并回滚。测试要用两个独立连接，而不是同一个会话里的两次提交。

有效主部门的查询条件是：指针存在，成员 `status=active`，`effective_from` 已到，`effective_to` 为空或未到。没有成员行，或指针落在失效行上，结果都是无组织授权。主管范围仍是 `manager_id` 指向该员工的组织及其 `parent_id` 下级；下属只含这些组织里的有效成员。`sys_user.department` 字符串不参与计算。

## 8. 服务身份与会话

服务不是员工，不写入 `sys_user`。

| 对象 | 表 | 作用 |
| --- | --- | --- |
| 客户端 | `auth_service_client` | `client_id`、显示名、状态、当前密钥哈希、上一代密钥哈希及其失效时间 |
| 允许的受众 | `auth_service_client_audience` | 该客户端可以申请的资源受众，一行一个 |
| 会话 | `auth_service_session` | `id` 就是服务令牌的 `sid`，另有 `client_id`、`signing_kid`、`expires_at`、`revoked_at` |

客户端密钥只存哈希。换凭证时新哈希立即生效，旧哈希最多再保留 1 小时，供正在部署的调用方切换。停用客户端时，状态改为停用，并撤销它的全部服务会话；已发出的 `service_access` 即使签名仍正确也不能用。

领取服务令牌的接口核对客户端编号和密钥，通过后写 `auth_service_session`，签发 `sub=svc:<client_id>`。验证时除 RS256、`iss`、`aud`、`token_use=service_access` 之外，必须把 `svc:` 后面的编号对上客户端，并确认会话未撤销、客户端仍启用。数字形式的 `sub` 不能进入这条路径。

服务令牌没有员工权限。它不能调用 `require_employee` 保护的路由，除非第 10 节的换票政策另有一条明确委托，并且同时出示用户自己的 access。没有这张政策就不存在委托。

## 9. Dify 安全身份传递

已登录工作台：浏览器只把门户 access 交给 8002。门户验证员工后，用服务端的 Dify 密钥发送语句。Dify 返回意图。门户再用已验证的员工主体调用原来的 service 和事务。Dify 密钥只说明调用方是门户，不说明员工是谁。模型看不到 JWT，也不能指定员工号。

公开 Chatflow：没有员工会话。只允许公开问答和事先列明的访客接口。员工写入在 8000 上保持 503。将来若要在公开流里写员工数据，必须先有已登录入口或安全代理。不能把固定的 Dify API Key 当成员工。

本轮不改已发布工作流，也不改生产认证配置。

## 10. Token Exchange 契约

当前没有已经确认的跨模块调用需求。本阶段只定契约，不注册路由，不开放换票。不提供“任意服务换成任意模块令牌”的通用接口。

将来若某个调用方需要换票，必须先有一条 `auth_token_exchange_policy`：调用方 `client_id`、源受众、目标受众、最长秒数、是否启用。没有这条记录就拒绝。

申请时同时出示两张仍有效的令牌：调用方自己的 `service_access`，以及被代表用户的 `access`。用户令牌的 `aud` 必须等于政策中的源受众，会话未撤销，`token_use=access`。新令牌保持同一 `sub` 和 `user_type`，使用新的 `sid` 并关联原会话，`aud` 只能是政策中的那一个目标，`exp` 不超过原令牌剩余时间和政策上限，设计上限为 5 分钟。新令牌不携带权限；目标模块仍从数据库读权限并执行自己的业务规则。换票不能把学生令牌换成员工受众，也不能把服务主体换成用户主体。

审计记下调用方客户端、用户 `sub`、源受众、目标受众和结果。政策未启用时，接口不存在，不能用配置开关临时打开。

## 11. 8000 业务开放验收清单

只完成 RS256 验签，不能打开 8000 的员工业务写入。下面每一项都要通过，并且 ENT 现有回归通过。

| 编号 | 开放前必须看到的结果 |
| --- | --- |
| N1 | 用公钥冒充 HS256 重签的 RS256 令牌被拒绝 |
| N2 | `ent-portal` 的 HS256 令牌在 8000 被拒绝 |
| N3 | 旧 ENT 令牌在 PF、CS、STU、RPT 路由被拒绝 |
| N4 | `edu-api:ent` 的 access 不能调用其他资源受众 |
| N5 | `service_access` 不能调用员工路由 |
| N6 | 带员工号或 `user_type` 的服务令牌被拒绝 |
| N7 | `alg=none` 被拒绝 |
| N8 | 未知或已停用 `kid` 被拒绝 |
| N9 | 学生令牌不能调用员工审批 |
| N10 | 见下文。账号类本身不能绕过数据范围 |
| N11 | 删除权限后，未过期令牌的下一次请求按新权限拒绝 |
| N12 | 令牌里的 `user_type` 与数据库当前值不一致时拒绝 |
| N13 | 会话库不可用时返回 503，而不是只验签名后放行 |
| N16 | 登出、停用、改密后的 access 和刷新串都失效 |
| N18 | 伪造员工头、Dify 对话变量和固定 Dify Key 都不能形成员工主体 |
| N19 | 访客调用 ENT 写入被拒绝，且不产生业务行 |
| 回归 | 8002 四角色、门户 AI 写入和全量 pytest 仍通过 |

N10 分三种情况，不能把所有管理员都写成无权，也不能让账号类本身成为授权：

- `user_type=admin`，角色没有业务模块明文授予的跨客户范围：访问他人客户仍拒绝。
- `user_type=employee` 且角色编码是 admin：账号类仍是员工，数据范围规则与上一行相同。
- 只有 ENT 已经实现并写明的管理范围权限，才允许落在该范围内的访问。今天的归属检查仍然有效；在 ENT 写出这种权限之前，不增加“管理员可看全部客户”的期望。

N14 和 N15 不在这张开放清单里。它们是启用 Refresh Token 之前的门槛：并发刷新必须撤销整个家族，重复使用旧刷新串必须撤销家族并要求重新登录。

开放方式只允许把 8000 配到 BASE 验签器，不接受 HS256。开放后用真实员工令牌做一条写入和一条越权，并核对业务行只增加被授权的那一条。

失败回滚：

1. 把 8000 的进程环境设回 `blocked` 并重启。不改 8002。
2. 确认 `/health` 为 200，无员工身份的业务请求为 503。
3. 核对开放窗口内的业务表计数，意外写入要按业务事务回滚或单独更正并记审计，不能留下未说明的行。
4. 若新 `kid` 已经签发过令牌，按第 12 节撤销这些会话。
5. 不把验签器留在“临时放开”的状态上排错。原因和计数写入事故记录后再决定是否重新验收。

## 12. 密钥、kid 与泄露处理

`ent_auth_session` 增加可空列 `signing_kid VARCHAR(64) NULL`。现有插入语句不写这一列，历史门户会话保持 NULL，旧数据不回填、不改名。新的 BASE 用户会话写入当时的 `kid`。`auth_service_session` 同样记录 `signing_kid`。刷新行通过 `session_id` 找到所属会话，不单独保存另一套密钥。

| 内容 | 存放位置 |
| --- | --- |
| `kid`、算法、状态、启用时间、退出验证时间、公钥 JWK | 密钥元数据表。没有私钥列 |
| 私钥 PEM | 仓库和数据库之外的文件。路径只出现在环境变量中，文件权限限于运行用户 |

正常轮换：新 `kid` 开始签发，旧 `kid` 标为“只验证”，保留时间等于 access 上限 60 分钟，仍出现在 JWKS 中。窗口结束后标为停用并从 JWKS 移除。停用的 `kid` 不再签发。

泄露：元数据立即标为已泄露，JWKS 马上去掉该公钥，并撤销 `signing_kid` 等于该值的用户会话、服务会话和对应刷新家族。已撤销会话即使公钥仍留在某个缓存里，也会在会话检查处失败。

JWKS 响应 `Cache-Control: max-age=60`。验签方遇到未知 `kid` 先刷新 JWKS；元数据已是泄露或停用的 `kid` 直接拒绝，不使用本地旧缓存。缓存最多影响签名层 60 秒，不能延长已撤销会话的寿命。只验签名、不查会话的部署不符合本设计，也不能用来打开 8000。

私钥文件泄露时的回滚就是上一节的进程回退，加上该 `kid` 的会话撤销。不把私钥写进报告、日志或数据库。

## 13. 五个业务模块接入计划

| 模块 | 身份 | BASE 提供 | 模块自己判断 | 现在的代码 |
| --- | --- | --- | --- | --- |
| PF | 员工 | `edu-api:pf` 的员工 access | 谁可以上传和查看研判 | 无研判路由 |
| CS | 访客与员工后台 | 访客无令牌；后台用员工 access | 哪些接口公开，哪些属于管理 | `modules/offer` 仍是占位 |
| ENT | 员工和管理员账号类 | 过渡期 8002 用旧令牌；新令牌用 `edu-api:ent` | 客户、日报、成绩、审批和已写明的管理范围 | 8002 已验收；8000 仍拒绝 |
| STU | 学生与处理申请的员工 | 两类主体互拒 | 学生能提交什么；员工能批哪些申请 | 学生包是占位；员工侧请假处理已存在 |
| RPT | 员工 | 身份；成员表完成后再提供组织范围 | 哪些报告行可见 | 统计包是占位 |

空包不算已接入。换票在对应政策写入之前不存在。

## 14. 分阶段任务与验收

可以同时做的只有不改变 8000 拒绝行为的准备。任何阶段都不用临时配置换取写入成功。

| 顺序 | 任务 | 验收 | 此阶段不做什么 |
| --- | --- | --- | --- |
| 1 | BASE-02 只读清单和远程认证 | 将提交与将忽略的路径分开；`.env` 不入库 | 不整目录 `git add`。可与 2 并行 |
| 2 | BASE-05 腾讯云启动记录 | 云上 `aiproject` 的 `/health` 和进程身份有记录 | 不用本机成功代替。可与 1 并行 |
| 3 | RS256、JWKS、`signing_kid`、固定算法验签器 | N1～N8 在隔离库通过 | 8000 仍是 `blocked` |
| 4 | 旧 HS256 只留在 8002 | N2、N3 通过；8002 旧登录仍可用 | 不做受众自动映射 |
| 5 | 8000 开放候选 | 第 11 节全部通过，含 ENT 回归 | 未通过则执行回滚，不保留半开状态 |
| 6 | Refresh Token | N14、N15、N16 通过后才启用 | 不把刷新当成 8000 的隐藏前置 |
| 7 | 服务客户端、服务会话和凭证轮换 | N5、N6 通过；停用后旧服务令牌失效 | 不把服务写入 `sys_user` |
| 8 | 学生登录 | 仅在第 3 节的 STU 事项确认后编码 | 不假定现有学生行都能登录 |
| 9 | 两张组织表 | 并发测试只留下一个主部门指针；无成员行无组织授权 | 不据此放开跨部门业务数据 |
| 10 | 五个模块按受众逐个接入 | 每个模块都有无令牌拒绝和越权拒绝 | 不把全部路由放进同一个受众 |
| 11 | 换票 | 只有已启用的单条政策可以通过；无政策时路由不存在 | 不提供通用换票 |
| 12 | Dify | 工作台仍由门户持有员工身份；公开流保持 N18、N19 | 不发布新的写库工作流 |

登录不需要 access。刷新只接受不透明刷新串，不接受 `edu-auth` JWT。JWKS 是公开的公钥接口，不需要任何令牌。登出使用正在作废的那张 access，受众是它原来的资源受众，而不是 `edu-auth`。列出会话或撤销其他会话时，才要求一张 `aud=edu-auth` 的员工 access；这个管理接口在有具体需求前不注册。因此 `edu-auth` 不是刷新和 JWKS 的入场券。

本轮没有修改业务代码、数据库、认证逻辑、生产配置和已发布工作流。等待最终复核；通过前不开始编码。
