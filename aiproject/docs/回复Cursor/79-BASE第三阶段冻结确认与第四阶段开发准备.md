# 79 BASE 第三阶段冻结确认与第四阶段开发准备

日期：2026-11-12  
结果：**第三阶段代码冻结。本轮只补上身份与会话绑定、连接失败即 503、以及过期 Access 才能用 Refresh 兜底登出。没有开放生产认证，没有进入第四阶段。**

GPT 已审核通过 78 号。下面三项里，授权读路径原来已经比对 `sub` 和会话用户；登出和刷新签发有真实缺口，数据库连接类异常也没有全部映射为 503。已做最小修复。修复后不再改第三阶段代码，等项目负责人明确安排再进入第四阶段。

## 1. 三项核实结果

### 1.1 JWT `sub` 与 `ent_auth_session.user_id`

签发时两者来自同一次身份解析。`resolve_identity` 把 `sub` 写成 `str(user_id)`。`start_session` 把 `identity.user_id` 写入 `ent_auth_session.user_id`，Access 的 `sub` 使用 `identity.sub`。

读路径拒绝错配：

| 函数 | 行为 |
| --- | --- |
| `_session_block` | `int(session.user_id) != int(claims["sub"])` 时返回 `invalid`，不更新 `last_used_at` |
| `require_live_session` | 同上，抛 `BaseSessionError("invalid")` |
| `access_matches_session` | 调用 `require_live_session` |
| `note_verified_access`、`authorize_access` | 经 `_session_block` 拒绝；`authorize_access` 还要求 `identity.sub == str(claims["sub"])` |
| `_end_known_session` | 本轮补上。有效 Access 的 `sub` 与会话 `user_id` 不一致时抛 `invalid`，不撤销该会话，也不改走 Refresh |
| `_foreign_binding` | 本轮补上。刷新串上的 `user_id` 与会话所有者不一致时，只撤销该刷新家族，不撤销别人的会话，也不签发新 Access |

测试：`test_access_subject_must_match_session_user`。用用户 10 的声明配上用户 15 的 `sid` 重新签名后，`note_verified_access`、`authorize_access`、`access_matches_session` 和 `end_login` 都返回 `invalid`。用户 15 的会话未被撤销，其刷新串仍可轮换，新 Access 的 `sub` 仍是 `"15"`。把用户 10 的刷新行改成 `user_id=15` 后再刷新，返回 `invalid`，用户 10 的会话和原 Access 仍有效。

### 1.2 连接断开和超时返回 503

`_STORE_UNAVAILABLE` 覆盖这些 SQLAlchemy 异常：`OperationalError`、`ProgrammingError`、`InterfaceError`、`DisconnectionError`（含连接池整体失效）、`TimeoutError`（连接池取连接超时）。`_session`、`_touch_last_used` 和 `_store` 遇到它们就回滚并抛 `BaseSessionUnavailable`。`session_failure_status` 把它映射为 503。

`authorize_access`、`note_verified_access`、`end_login` 和 `access_matches_session` 都走上述路径。异常抛出后不返回已通过签名校验的声明，也不把登出说成已经完成。MySQL 驱动报告的断连、服务器消失和查询超时，仍落在 `OperationalError` 上，原有映射继续有效。

测试：

| 测试 | 结果 |
| --- | --- |
| `test_database_failure_rejects_instead_of_accepting_the_signature` | `OperationalError` 在读会话、更新 `last_used_at`、重读身份和登出时均为 503。会话未撤销，`last_used_at` 不变 |
| `test_disconnect_and_timeout_fail_closed` | `InterfaceError`、`DisconnectionError`、连接池 `TimeoutError` 各一组。授权和登出均为 503，会话未撤销，`last_used_at` 不变 |

这仍不是 HTTP 路由，没有接入 ENT。

### 1.3 只有真正过期的 Access 才能用 Refresh 兜底登出

`verify_token` 的校验没有放宽。新增 `verify_expired_access`：签名、`iss`、`aud`、算法、`kid`、`token_use` 和其他 Access 声明仍须通过，只跳过 `exp` 与当前时间的比较；若 `exp` 尚未过去，仍然拒绝。

`end_login` 经 `_presented_access` 分类：

| Access | 处理 |
| --- | --- |
| 缺失或空字符串 | 可以按原规则使用 Refresh |
| `verify_token` 通过 | 撤销该 `sid`，且 `sub` 必须等于会话 `user_id`。不因为同时带了 Refresh 而新建会话 |
| 签名、`iss`、`aud` 等检查通过，只有 `exp` 已过期 | 不轮换、不签发，按 Refresh 的 `family_id` 撤销 |
| 错误签名、错误 `iss`、错误 `aud`，包括“已经过期但受众也不对” | 抛 `BaseTokenError`。`session_failure_status` 为 401。不使用 Refresh，不撤销会话 |

PyJWT 会先报 `exp` 再报受众，所以不能把 `ExpiredSignatureError` 单独当成“只是过期”。`verify_expired_access` 在关闭过期检查后仍校验 `iss` 和 `aud`。

测试：`test_refresh_logout_accepts_only_a_genuinely_expired_access`。错误签名、错误 `iss`、错误 `aud`、以及受众错误且 `exp` 已过期的 Access，在带有未过期 Refresh 时都拒绝，会话保持。签名、`iss`、`aud` 正确且 `exp` 已过期的 Access 仍返回 `revoked`。原有 `test_logout_revokes_without_creating_a_session` 继续通过。

## 2. 第三阶段最终代码清单

本轮改动只在前三行。其余文件保持 78 号已认可的内容。

| 文件 | 角色 |
| --- | --- |
| `aiproject/app/core/security/base_jwt.py` | RS256。本轮增加 `verify_expired_access` |
| `aiproject/app/core/security/base_session.py` | 会话、刷新、撤销、授权、登出。本轮补绑定、503 和登出分类 |
| `aiproject/tests/modules/test_base_session_acceptance.py` | 本轮三项测试 |
| `aiproject/app/core/security/jwks_router.py` | 第一阶段 JWKS |
| `aiproject/app/core/security/base_identity.py` | 第二阶段只读身份 |
| `aiproject/app/core/security/base_session_schema.py` | `ent_auth_session`、`auth_refresh_token`、`auth_user_session_kid` |
| `aiproject/migrations/pending/003_base_refresh_token.sql` | 待批准，未执行 |
| `aiproject/migrations/pending/003_base_refresh_token_rollback.sql` | 对应回滚，未执行 |
| `aiproject/tests/modules/test_base_session.py` | 会话与轮换 |
| `aiproject/tests/modules/test_base_session_mysql.py` | 临时库并发 |
| `aiproject/tests/modules/test_base_identity.py` | 身份 |
| `aiproject/tests/modules/test_base_jwt.py` | RS256 |
| `aiproject/tests/modules/test_identity_settings.py` | 身份开关回归 |
| `aiproject/tests/integration/test_ent_portal_routes.py` | 门户路由回归 |

没有修改 ENT 8002、`AuthService`、`credentials.py`、Cookie、路由注册、`.env` 或待执行 DDL。64～78 号报告没有覆盖。

## 3. 全部测试结果

解释器：`aiproject/.venv313`。没有运行会改业务数据的客户验收脚本，也没有对 `education_service` 执行 DDL。

| 范围 | 结果 |
| --- | --- |
| `test_base_session.py`、`test_base_session_acceptance.py`、`test_base_session_mysql.py` | 24 通过 |
| `test_base_identity.py`、`test_identity_settings.py`、`test_ent_portal_routes.py` | 17 通过 |
| `test_base_jwt.py` | 18 通过 |

合计 59 通过，0 失败。其中本轮新增 5 项：身份绑定 1 项，连接断开与超时 3 项，登出分类 1 项。MySQL 8.0.27 临时库并发测试仍通过，临时库由测试删除。

## 4. 最终 Git 状态和 Hash

分支：`feature/base02-safe-baseline`。没有 reset、clean、rebase、amend、整目录添加或推送。

| 提交 | Hash | 内容 |
| --- | --- | --- |
| 78 号报告 | `4ffefb17a1a6193335696b86a95149ade5a6f1a4` | 本轮起点 |
| 78 号已保留的代码 | `8bac3fe17fc8a3197d7537815812be3f1038f56a` | 仍是祖先 |
| 本轮代码 | `3fdf73995abb93dfbac272a4c00c5828aba6555f` | 身份绑定、连接失败 503、过期 Access 才可兜底登出 |
| 本报告首次入库 | `6a917281bd1cc4a3428cff29d2625826552bf07a` | 79 号正文和索引首行 |

`6a917281bd1cc4a3428cff29d2625826552bf07a` 只包含本文件和 `00-文件索引与阅读顺序.md` 的首行。随后的提交只把这一行 Hash 写进本文件，不改代码。代码冻结点是 `3fdf73995abb93dfbac272a4c00c5828aba6555f`。

未跟踪且未纳入提交：71、72、74 号报告，会话交接说明，以及 `backend/`、仓库根目录 `docs/`、`教育服务_0914/`。

## 5. 第三阶段遗留的生产启用条件

这些条件都还没有做。未批准前不执行。

1. 在维护窗口执行 `003_base_refresh_token.sql`。回滚先删 `auth_user_session_kid`，再删 `auth_refresh_token`，然后只删 `parent_session_id` 和 `last_used_at`。不删 `ent_auth_session`，不删原列和原有会话行。
2. 批准门户 Origin 和 CSRF 后，再挂只接受 POST 的刷新和登出。刷新调用 `refresh_session`，登出调用 `end_login`。正式环境 Refresh Cookie 用 `__Secure-` 前缀，CSRF 用 `__Host-` 前缀。Access 只放内存。
3. 改密、重置、停用和角色停用改为在现有事务里调用 `revoke_user_sessions`，并且只撤目标用户。不要在那些事务里调用 `revoke_all_sessions`。
4. 受保护业务路由调用 `authorize_access`。数据库异常用 `session_failure_status` 返回 503。
5. 单独批准 7 天清理的调度和失败告警。当前没有生产定时任务。
6. 8000 保持 blocked，学生登录保持关闭，ENT 8002 保持 HS256。

## 6. 第四阶段开发范围

本轮不开始第四阶段。范围以 64 号最终稿和补充修订版为准，不改总体设计。

1. 服务客户端、服务会话和凭证轮换。服务身份不写入 `sys_user`。停用后旧服务令牌失效。
2. 两张组织表和成员关系。并发下只留一个主部门指针。现有 `department` 字符串不是组织成员，不得插入 `sys_org_member`。
3. 换票只接受已启用的单条政策。无政策时不注册路由。服务令牌的受众必须是 `edu-auth:token-exchange`。委托会话不能再作为换票源，不能嵌套。

五个模块按受众接入、Dify 身份传递、8000 开放、学生登录和腾讯云部署，都不在第四阶段的开工范围内。它们仍要等各自的前置条件。
