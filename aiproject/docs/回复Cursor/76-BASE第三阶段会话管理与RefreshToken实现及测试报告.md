# 76 BASE 第三阶段会话管理与 Refresh Token 实现及测试报告

日期：2026-11-12  
结果：**BASE 已能在隔离库里创建会话、轮换一次性刷新串，并按范围撤销。真实数据库没有执行迁移。ENT 8002 仍使用 HS256。**

没有重写第一阶段 RS256，也没有改第二阶段身份解析的规则。学生登录没有开放，8000 仍是 blocked。

## 1. 64 号架构对应情况

以最终复核版第 6 节和最终补充修订版为准。补充修订版取代了“会话上只保存一个 `signing_kid`”的做法，所以本阶段不给 `ent_auth_session` 增加这一列。

| 架构要求 | 实现 |
| --- | --- |
| 刷新串是 256 位随机值，不是 JWT | `secrets.token_bytes(32)`，再做 URL-safe Base64 |
| 只存 SHA-256 | 主键 `token_hash` 是十六进制摘要 |
| `family_id`、`session_id`、`user_id`、`expires_at`、`used_at`、`revoked_at`、`replaced_by` | 表 `auth_refresh_token` |
| 同一事务里轮换；已使用或已撤销则撤销整族和会话 | 条件更新认领，失败则整族撤销 |
| 并发时后到的请求看到 `used_at`，整族作废，之后必须重新登录 | 隔离库并发测试已覆盖 |
| 会话与密钥是多对多 | 新表 `auth_user_session_kid`，主键 `(session_id, kid)`，另有 `kid` 索引 |
| 刷新串默认 12 小时、上限 14 天；会话绝对寿命默认 12 小时、上限 7 天；空闲默认 2 小时、上限 12 小时 | 超过上限直接拒绝 |
| 新刷新串不能晚于会话绝对结束时间 | `expires_at` 取较早的那个 |
| 登出撤当前会话及其刷新族；停用和改密撤该用户全部会话和刷新族 | 两个独立函数，测试确认不会波及其他用户 |
| 密钥停用撤用过该 `kid` 的会话 | `revoke_sessions_for_kid` |
| 换票、服务会话、组织成员 | 本阶段不做 |

早期草稿里的 `POST /api/v1/auth/refresh` 没有被后来的 64 号文件改名，但也没有在最终文本里再次写成必须立即注册的路由。最终文本要求刷新和登出只接受 POST，并核对 Cookie、`Origin` 和 CSRF。这些运行配置还没有批准，所以本阶段只实现服务函数，不往现有应用上挂新路由。

## 2. 修改前代码结构

修改前 HEAD 是 `a792edfe9553b4d838378edac3a3fe6e4502871a`。

`ent_auth_session` 实际列仍是 `id`、`user_id`、`expires_at`、`revoked_at`、`create_time`。ENT 的 `AuthRepository.create_session` 按这些列插入。没有 `auth_refresh_token`，也没有 `auth_user_session_kid`。身份解析在 `base_identity.py`，RS256 在 `base_jwt.py`。

## 3. Session 会话实现

`start_session` 只接受第二阶段解析后仍允许走现有 ENT 登录的账号，也就是 `employee` 和 `admin`。学生会被拒绝，并且不会留下刷新行。

`sid` 是新生成的 36 位小写 UUID，写入 `ent_auth_session.id`，同时放进 RS256 access 的 `sid`。会话行还写 `user_id`、`create_time`、`expires_at` 和 `last_used_at`。`expires_at` 是会话绝对结束时间，不是 access 的 60 分钟。

伪造的 `sid` 在 `require_live_session` 里拒绝。过期或已撤销的会话不能继续刷新。

## 4. Refresh Token 生成方式

每次签发和每次成功轮换都调用 `secrets.token_bytes(32)`。返回给调用方的是编码后的字符串。它不是 JWT，没有 `token_use`。

## 5. SHA-256 存储方式

入库前对调用方持有的那个字符串做 SHA-256，保存 64 位十六进制。测试确认原文不在任何 `token_hash` 里，摘要也不等于原文。

## 6. 令牌轮换机制

一个事务内：

1. 按摘要锁定刷新行。MySQL 使用 `SELECT … FOR UPDATE`。SQLite 没有该语法，隔离测试靠“只更新尚未使用且未撤销的行”保证只有一个请求能认领。
2. 认领成功才检查有效期、会话、空闲时间和当前身份。
3. 仍可用：写入 `used_at` 和 `replaced_by`，插入同一 `family_id` 的新摘要，并签发新的 RS256 access。
4. 新刷新串的结束时间不会晚于会话的 `expires_at`。

找不到摘要时返回无效，不签发。

## 7. 重放攻击处理

已经带有 `used_at` 或 `revoked_at` 的刷新串再次出现时，撤销该 `family_id` 的全部刷新行和对应会话，然后拒绝。因此成功轮换后，旧串不能再用；一旦旧串被重放，新串也一起失效，调用方必须重新登录。

## 8. 并发刷新保护

两个线程同时提交同一刷新串。结果一个得到新串，另一个得到 `replay`。事务结束后，新串也不能再刷新，会话已被撤销。另一个用户的刷新串不受影响。

## 9. 会话撤销机制

| 场景 | 函数 | 范围 |
| --- | --- | --- |
| 退出当前会话、撤销单个会话 | `revoke_session` | 该会话、以它为父会话的行，以及这些会话的刷新族 |
| 停用账号、修改密码、账号或角色不再可认证 | `revoke_all_sessions` | 只撤这个 `user_id` 的会话和刷新族 |
| 刷新重放 | 刷新函数内部 | 该家族和对应会话 |
| 签名密钥停用 | `revoke_sessions_for_kid` | 只用过这把 `kid` 的会话及其刷新族 |

这些函数各自提交自己的事务。本阶段没有把它们接到 `AuthService.change_password` 或登录里，避免改变现有 ENT 行为。调用点留到以后单独接入。

停用用户和停用角色在刷新时会重新调用第二阶段的身份解析。解析失败就撤销该家族和会话，不签发新 access。

## 10. 接口设计

没有注册新的 HTTP 路由，也没有替换 `POST /api/v1/auth/logout`。

建议等 DDL 批准、门户来源和 CSRF 配置确定后再挂：

| 能力 | 建议 | 理由 |
| --- | --- | --- |
| 刷新 | `POST /api/v1/auth/refresh` | 最早的 64 号草稿使用这个路径，后来的文件没有改名；只接受刷新串，不接受 JWT |
| 退出当前会话 | 继续使用现有登出路径，内部再调 `revoke_session` | 现在的登出走 HS256。直接替换会破坏 8002 |
| 撤销单个会话 | 与退出当前会话同一个函数 | 不另开一套路径 |
| 撤销用户全部会话 | 暂不注册公开接口 | 最终复核版写明，列出会话或撤销其他会话的管理接口在有具体需求前不注册。停用和改密以后在服务端内部调用 |

刷新和登出按 64 号只接受 POST，并在挂路由时核对 `Origin`、CSRF Cookie 和 `X-CSRF-Token`。GET 不执行刷新或登出。

## 11. 数据库迁移 DDL

文件：`aiproject/migrations/pending/003_base_refresh_token.sql`。

内容是：

- `ent_auth_session` 增加可空列 `last_used_at`、`parent_session_id`。
- 新建 `auth_refresh_token`。
- 新建 `auth_user_session_kid`，含 `idx_user_session_kid (kid)`。
- 不增加 `signing_kid`。
- 不创建服务会话表，也不创建组织表。

现有 ENT 插入语句写出了原有列名，新列保持 NULL，因此批准后的变更不要求改旧插入。

这个文件没有对 `education_service` 执行。

## 12. 回滚方案

文件：`aiproject/migrations/pending/003_base_refresh_token_rollback.sql`。

先删除两张新表，再删除新增的两个可空列。不删除 `ent_auth_session`，也不改它原来的五列。回滚同样等待批准，本次没有执行。

执行前仍应先做库备份。MySQL 的 DDL 不能靠一个普通事务自动撤销，所以上面的回滚脚本就是反向操作。

## 13. 自动化测试结果

命令：

`aiproject/.venv313\Scripts\python.exe -m pytest tests/modules/test_base_session.py tests/modules/test_base_identity.py tests/modules/test_identity_settings.py tests/modules/test_base_jwt.py::test_ent_portal_hs256_remains_unchanged tests/integration/test_ent_portal_routes.py -q --tb=line`

结果：**25 passed**。会话文件 7 项，其余是身份映射和 ENT 回归。使用内存或临时 SQLite，并禁止连接生产引擎。没有客户 E2E。

要求中的情况对应：

| 编号 | 情况 | 测试 |
| --- | --- | --- |
| 1–3 | 256 位生成、原文不入库、只存 SHA-256 | `test_refresh_secret_is_256_bits`、`test_refresh_is_random_hashed_and_rotates` |
| 4–6 | 正常刷新、旧串失效、新串生效 | 同一轮换测试 |
| 7–8 | 过期、不存在 | `test_expired_refresh_and_session_are_rejected`、轮换测试中的缺失串 |
| 9–10 | 重放、家族撤销 | 轮换测试里第二次使用旧串后，新串也失败 |
| 11–12 | 并发只有一个认领成功、用户隔离 | `test_concurrent_refresh_keeps_one_winner_then_revokes_family`、`test_revoked_session_disabled_user_and_role_are_rejected` |
| 13–16 | 建会话、sid、会话过期、已撤销 | 轮换、过期和撤销测试 |
| 17–18 | 停用用户、停用角色 | 撤销测试 |
| 19–20 | 全部会话撤销、单会话不影响其他会话 | 撤销测试 |
| 21–25 | RS256、kid、sid、token_use、刷新串不能当 access | `test_users_and_kids_stay_isolated` |

## 14. ENT 兼容性

没有修改 `AuthService`、`credentials.py` 和登录路由。

| 检查 | 结果 |
| --- | --- |
| 学生可识别，现有登录仍拒绝，员工登录仍是 HS256 | 通过 |
| 门户 HS256 签发与验证 | 通过 |
| 默认身份模式 blocked | 通过 |
| 隔离 SQLite 上的认证路由 | 通过 |

## 15. Git 分支和提交 Hash

分支：`feature/base02-safe-baseline`。

会话实现、测试和待执行 DDL 的提交是 `04fd256d31f85083a79b342795793707cf7c1f90`。父提交是 `a792edfe9553b4d838378edac3a3fe6e4502871a`。身份映射提交 `1982dda06f189962028152e4b140b4f43cf0c23e` 仍在。

没有 `reset`、`clean`、`rebase`、`filter-repo`、`amend`、`git add .` 或推送。

## 16. 尚未完成的工作

1. 真实库迁移尚未执行，等待审核 `003_base_refresh_token.sql`。
2. 刷新和登出的 HTTP 路由、Cookie 和 CSRF 还没有挂上。
3. 停用账号和修改密码还没有改去调用 `revoke_all_sessions`，以免改动现有 ENT。
4. 过期数据的 7 天清理任务还没有调度。
5. 服务会话、换票和组织成员不在本阶段。
6. 五个模块接入、Dify 身份传递、8000 开放和腾讯云部署继续暂停。
