# 77 BASE 第三阶段最终安全验收与启用前缺口清单

日期：2026-11-12  
结果：**第三阶段已有实现全部保留。本轮补上了空闲时间、密钥关联、生命周期边界和过期清理，并在独立的 MySQL 8.0.27 临时库上验证了并发刷新。生产认证没有开放，真实库没有执行迁移，ENT 8002 没有改动。**

请 GPT 审核本报告。下一阶段等新的指令，本轮不进入第四阶段。

## 1. 64 号架构对应情况

对照的是最终复核版、最终补充修订版，以及《64-BASE最终实施前技术细节确认》。后两份取代了“在 `ent_auth_session` 上只保存一个 `signing_kid`”的旧写法。架构本身没有改写。

| 64 号要求 | 本轮位置 |
| --- | --- |
| 刷新串 256 位随机值，只存 SHA-256，一次性轮换 | 保留 `04fd256`，未重写 |
| 并发后到者看到 `used_at`，撤销整族和会话 | MySQL 8.0.27 临时库已验证，见第 2 节 |
| `last_used_at` 条件更新，间隔 5 分钟；失败不延长会话 | `note_verified_access`、`_touch_last_used`，见第 3 节 |
| 一个 `sid` 可对应多把 `kid` | `auth_user_session_kid`，见第 4 节 |
| Access 60 分钟；刷新默认 12 小时、上限 14 天；会话绝对寿命默认 12 小时、上限 7 天；空闲默认 2 小时、上限 12 小时；保留期固定 7 天 | 上限拒绝和保留期已测，见第 5、6 节 |
| 停用、改密撤销该用户全部会话 | 函数已有，入口未接，见第 7 节 |
| Cookie、CSRF、只接受 POST | 未挂路由，清单见第 8 节 |
| 待执行 DDL 与回滚 | 只复核，未执行，见第 9 节 |

已完成并保留：第一阶段 RS256、第二阶段 `base_identity.py`、第三阶段 `base_session.py`、`auth_refresh_token`、`auth_user_session_kid`、`003_base_refresh_token.sql` 和对应回滚脚本。

## 2. MySQL 并发验证结果

已验证。测试使用本机 MySQL 8.0.27，单独创建临时库 `base_p3_` 加 12 位随机后缀，字符集 `utf8mb4`、排序规则 `utf8mb4_unicode_ci`。测试结束执行 `DROP DATABASE`。没有连接 `education_service` 做写入，没有改 MySQL 服务、密码、`.env` 或账号，也没有动 ENT 8002。

临时库先按当前生产形状创建 `ent_auth_session`，再执行待审的 `003_base_refresh_token.sql`。两个独立连接同时刷新同一枚刷新串：

- 方言不是 SQLite，锁定语句带 `SELECT ... FOR UPDATE`。
- 一个请求认领成功，另一个返回 `replay`。
- 原记录的 `used_at` 已写入。
- 该 `family_id` 的全部刷新行都有 `revoked_at`，包括胜出请求刚签发的新刷新串。
- 对应 `ent_auth_session.revoked_at` 已写入。
- 另一名用户的会话仍可刷新，且没有被撤销。
- 两个线程都正常结束，没有死锁、锁等待超时或部分提交。

同一次临时库还核对了：`ent_auth_session` 没有 `signing_kid`；`id` 与 `auth_user_session_kid.session_id` 都是 `varchar(36)`、`utf8mb4_unicode_ci`；主键是 `(session_id, kid)`；另有独立索引 `idx_kid`。

## 3. last_used_at 更新情况

三层要分开看。

**Session Service 已实现。** 成功创建会话时写入 `last_used_at`。成功刷新调用 `_touch_last_used`。`note_verified_access` 供将来的 BASE 业务验证使用：先做 RS256 校验，再在同一事务里判断会话。只有空闲或绝对时间已到才撤销整族和会话；否则仅当 `last_used_at` 为空，或早于当前时间 5 分钟以上，才更新。条件更新没有改到行时，旧时间保留，空闲判断不会被延后。

**已经接入的请求验证：没有。** 现有 `access_matches_session` 只做结构核对，不写 `last_used_at`。ENT 8002 的 HS256 登录、`require_employee` 和现有 logout 都没有调用 `note_verified_access`。

**将来挂载路由时要接入。** BASE 业务请求在校验 access 之后调用 `note_verified_access`。只调用 `access_matches_session` 不会推进空闲时间，也不会在空闲到期时撤销家族。刷新路由调用现有 `refresh_session`，其中已经包含条件更新。

隔离 SQLite 已确认：1 分钟内的再次验证不改时间；满 6 分钟后写入新时间；刷新后 1 分钟内再次刷新仍保留上一次时间；空闲超过 2 小时返回 `expired`，整族和会话都被撤销。

## 4. kid 多对多关联验证

创建会话时，`_issue` 与刷新行插入在同一个事务里记录当前 `kid`。刷新轮换签发新 access 时记录新 `kid`。同一 `(session_id, kid)` 已存在时不更新，`first_issued_at` 保持首次时间。

SQLite 测试：同一会话先用 K1 再轮换到 K2，两条关联都在；再次使用 K2 不改 K2 的 `first_issued_at`。若关联写入失败，整次刷新回滚，原刷新串仍可使用。`revoke_sessions_for_kid("base-current")` 撤销用过 K1 的会话及其刷新族；只使用 K2 的另一会话仍可刷新。

SQLite 元数据确认主键 `(session_id, kid)` 和索引 `idx_kid`。MySQL 临时库确认类型、字符集、排序规则与 `ent_auth_session.id` 一致。没有给 `ent_auth_session` 增加 `signing_kid`。

## 5. 生命周期边界测试

| 项目 | 默认 | 最大 | 测试 |
| --- | ---: | ---: | --- |
| Access Token | 60 分钟 | 60 分钟 | `exp - iat` 为 3600 秒 |
| Refresh Token | 12 小时 | 14 天 | 上限再加 1 秒，创建被拒绝 |
| 会话绝对寿命 | 12 小时 | 7 天 | 上限再加 1 秒，创建被拒绝；绝对结束时间等于 `create_time` 加配置寿命 |
| 空闲超时 | 2 小时 | 12 小时 | 上限再加 1 秒，刷新被拒绝；超时撤销整族 |
| 过期或撤销保留 | 7 天 | 固定 7 天 | 保留期内旧串仍返回 `replay`；清理之后同一哈希返回 `invalid` |

刷新串的 `expires_at` 不会晚于会话绝对结束时间。会话绝对时间从 `create_time` 计算，空闲时间从 `last_used_at` 计算。当前没有 HTTP 路由，所以 `invalid` 由服务错误码表达，还没有映射成 HTTP 401。

## 6. Refresh Token 清理服务

新增 `purge_expired_families`。它只删除“每一行都已过期或撤销，并且超过 7 天保留期”的家族，按 `family_id` 在一个事务里删除刷新行，再删除已无刷新引用且自身也超过保留期的会话。未配置生产定时任务。

隔离 SQLite 覆盖：

- 未过期令牌不删。
- 刚过期、仍在 7 天内的令牌不删，刷新仍返回 `expired`。
- 保留期内的旧令牌不删，重放仍返回 `replay`。
- 超过 7 天且整族都已过保留期的家族被整族删除，之后同一哈希返回 `invalid`。
- 家族里还有需要用于重放判断的记录时，整族保留。
- 删除会话失败时事务回滚，刷新行不会先被删掉。
- 其他仍有效会话不受影响。

## 7. 账号停用及密码修改联动方案

`revoke_all_sessions(user_id)` 已实现，并会撤销该用户的会话和刷新族。本轮没有修改 `AuthService.login`、密码流程或 HS256。

现有入口只撤销 ENT 门户会话，尚未调用 BASE：

| 入口 | 当前位置 | 将来要调用 |
| --- | --- | --- |
| 用户修改密码 | `AuthService.change_password` | 同一事务调用 `revoke_all_sessions(当前用户)` |
| 用户密码重置 | `AuthService.reset_password` | 同一事务调用 `revoke_all_sessions(目标用户)` |
| 用户停用 | `AuthService.update_user`，且 `status != normal` | 同一事务调用 `revoke_all_sessions(目标用户)` |
| 角色停用 | `AuthService.save_role` | 角色 `status != 1` 时，只对该角色下的用户逐个调用 `revoke_all_sessions` |

刷新时已经重新解析身份。账号停用、角色停用或不再是 `employee`/`admin` 时，该用户的刷新返回 `denied`，并撤销正在刷新的家族和会话。`note_verified_access` 不重新读角色，所以角色停用后的 access 要靠上面的撤销联动失效，不能只依赖下一次刷新。

后续测试方案，仍不改 ENT：

- 修改或重置用户 A 的密码后，A 的全部刷新族不可用，用户 B 的会话仍可刷新。
- 停用用户 A 后结果相同。
- 停用角色后，只撤销该角色下的用户；其他角色的用户仍可刷新。
- 断言调用参数只有目标 `user_id`，没有全表撤销。

## 8. Cookie 和 CSRF 接入清单

本轮不挂载新路由，不替换现有 logout，不改 ENT 8002，不开放刷新串的生产使用，不改 Cookie 配置，不开放学生登录，8000 继续 blocked。

将来批准门户来源和 CSRF 配置后再接入：

1. 只增加 `POST` 刷新和 `POST` 登出。GET 不执行这两件事。
2. 核对 `Origin` 等于已批准的门户来源。
3. CSRF Cookie 与请求头 `X-CSRF-Token` 必须一致。缺 Origin、来源不对或两个值不一致，都拒绝。
4. 正式环境 CSRF Cookie 使用 `__Host-` 前缀：`Secure`、`Path=/`、不设置 `Domain`、`SameSite=Strict`、不设置 `HttpOnly`。
5. Refresh Cookie 使用 `__Secure-` 前缀：`Secure`、`HttpOnly`、`SameSite=Strict`、`Path=/api/v1/auth`、不设置 `Domain`。
6. 只有环回主机且浏览器拒绝 `Secure` 时，才允许本地关闭 `Secure`；这时不用 `__Host-` / `__Secure-` 前缀，并改用仅限本地的 Cookie 名。非环回主机不关闭 `Secure`。
7. Access Token 只放内存，用 `Authorization: Bearer` 发送，不进 Cookie，也不进 `localStorage`。Bearer 访问不额外做这组 CSRF 检查。
8. 刷新调用 `refresh_session`。登出调用 `revoke_session`，撤销当前会话、子会话和对应刷新族。
9. 服务错误码 `invalid`、`replay`、`expired`、`revoked`、`denied` 映射为 HTTP 401。

## 9. DDL 与回滚审核

`003_base_refresh_token.sql` 和 `003_base_refresh_token_rollback.sql` 仍在 `migrations/pending/`。本轮没有执行。

正向脚本：

- `ent_auth_session` 只新增可空的 `last_used_at` 和 `parent_session_id`。`parent_session_id` 为 `VARCHAR(36)`，`utf8mb4_unicode_ci`。
- `auth_refresh_token` 含 `token_hash`、`family_id`、`session_id`、`user_id`、`expires_at`、`used_at`、`revoked_at`、`replaced_by`。`token_hash` 为主键。索引为 `idx_refresh_family`、`idx_refresh_session`、`idx_refresh_user`。外键指向 `ent_auth_session(id)`。
- `auth_user_session_kid` 含 `session_id`、`kid`、`first_issued_at`。主键 `(session_id, kid)`，独立索引 `idx_kid`，外键指向 `ent_auth_session(id)`。`session_id` 与 `ent_auth_session.id` 同为 `VARCHAR(36)`、`utf8mb4_unicode_ci`。
- 语句正文没有 `signing_kid`。没有删除或改名原有列。旧 ENT 插入仍只写原来的五列，新列保持 NULL。

回滚顺序：先删 `auth_user_session_kid`，再删 `auth_refresh_token`，然后只删除 `parent_session_id` 和 `last_used_at`。不删除 `ent_auth_session`，也不删除原来的会话行。

MySQL 临时库执行的是这份正向脚本，用完已删除临时库。`education_service` 未执行这份 DDL。

## 10. 全部测试结果

解释器：`aiproject/.venv313`。没有运行会改业务数据的客户验收脚本。

| 范围 | 结果 |
| --- | --- |
| `test_base_session.py`、`test_base_session_acceptance.py`、`test_base_session_mysql.py` | 15 通过 |
| `test_base_identity.py`、`test_base_jwt.py`、`test_identity_settings.py`、`test_ent_portal_routes.py` | 35 通过 |

合计 50 通过，0 失败。身份、RS256、HS256 门户路由和 8000 blocked 的回归仍通过。

## 11. Git 最终状态和提交 Hash

分支：`feature/base02-safe-baseline`。没有推送，没有 reset、clean、rebase、filter-repo、amend，也没有 `git add .`。

| 提交 | Hash | 内容 |
| --- | --- | --- |
| 本轮代码 | `ae641f0aca42e165f47db013200bd9c86cd571a0` | 空闲更新、清理服务、`idx_kid`、验收测试和 MySQL 并发测试 |
| 父提交 | `18dfb91c7b885c0c8e61960beeac946c66b1944c` | 76 号报告 |
| 第三阶段实现 | `04fd256d31f85083a79b342795793707cf7c1f90` | 仍是祖先，未改写 |
| 第二阶段报告 | `a792edfe9553b4d838378edac3a3fe6e4502871a` | 仍保留 |

未跟踪且未纳入本次提交：71、72、74 号报告，以及 `backend/`、`docs/`、`教育服务_0914/`。64 至 76 号报告没有被覆盖。

## 12. 尚未完成的启用条件

以下条件完成前，不开放生产认证：

1. 批准并在维护窗口执行 `003_base_refresh_token.sql`。当前真实库还没有这两张新表，也没有 `last_used_at`。
2. 批准门户 Origin 和 CSRF 运行配置后，再按第 8 节挂载 POST 路由。
3. 按第 7 节把改密、重置、停用和角色停用接上 `revoke_all_sessions`，并完成该节的隔离测试。
4. 清理函数已实现，但没有生产定时任务。启用前还要单独批准调度方式和失败告警。
5. 服务会话、换票和组织成员仍属于后续阶段。
6. 8000 保持 blocked。学生登录保持关闭。ENT 8002 保持 HS256。
7. 腾讯云工作继续暂停，直到五个模块合并并共同验收。
