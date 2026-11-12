# 78 BASE 第三阶段最终复核补充与第四阶段启动条件

日期：2026-11-12  
结果：**第三阶段实现继续保留。本轮只补上事务边界、请求级授权顺序、登出规则和数据库失败即拒绝。没有开放生产认证，没有进入第四阶段。**

请 GPT 做最终审核。

## 1. 事务兼容性

`revoke_all_sessions` 目前会自己管理事务。它通过 `_transaction` 在调用方没有事务时开启事务，并在结束时提交；调用方已经处于事务中时，它也会提交。

76 号和 77 号的差别就在这里。76 号说这些撤销函数各自提交，描述的是现在这个独立入口，这句话仍然成立。77 号要求改密或停用时“在同一事务里调用 `revoke_all_sessions`”。如果真的这样调用，密码修改会被这个函数提前提交，调用方后面的失败也不能把撤销和密码修改一起回滚。

因此两个入口分开：

| 入口 | 事务 | 用途 |
| --- | --- | --- |
| `revoke_user_sessions(db, user_id)` | 不开启、不提交、不回滚 | 传入调用方已经打开事务的 Session，也就是当前这条连接 |
| `revoke_all_sessions(db, user_id)` | 自己提交 | 没有外层事务时的独立调用 |

`revoke_user_sessions` 在 Session 没有打开事务时直接拒绝，避免悄悄变成另一次提交。将来改密、重置密码、停用账号或停用角色时，调用的是 `revoke_user_sessions`，由现有 `AuthService` 在自己的事务末尾提交一次。不要在那些事务里调用 `revoke_all_sessions`。

本轮没有修改 `AuthService.change_password`、`reset_password`、`update_user`、`save_role` 或 HS256。

隔离测试确认：没有外层事务时底层函数拒绝，原刷新串仍可用；调用方中途失败并回滚后，撤销不会留下；调用方提交后，另一个连接才看得到撤销；其他用户不受影响；`revoke_all_sessions` 仍然自己提交。

## 2. 请求级身份与权限验证

将来的 BASE 受保护请求按这个顺序，不能停在签名或 `note_verified_access`：

1. 校验 RS256 access：签发者、受众、有效期、`sid`、`sub` 和 `token_use`。
2. 从数据库读取会话。不存在、已撤销、超过绝对寿命或空闲超时，都拒绝。空闲或绝对到期时撤销该刷新家族和会话。
3. 重新读取该 `sub` 的账号状态、账号类型、角色和角色状态。
4. 重新读取角色权限，并确认本请求所需权限目前仍在其中。
5. 以上都通过后，才按 5 分钟条件更新 `last_used_at`。
6. 任一步数据库不可用，回滚并按第 4 节拒绝，不返回授权结果。

`authorize_access` 执行这个顺序。`note_verified_access` 只做会话存活和空闲时间，不读角色和权限。测试里，账号已经停用时它仍返回原声明；同一枚签名有效的 access，在没有权限、账号停用、类型改为学生或角色停用时，`authorize_access` 都返回 `denied`。权限被取消后不会改写 `last_used_at`。令牌里的 `user_type` 不能代替数据库里的权限。

没有挂载新的 HTTP 路由。将来路由返回 401 的是 `BaseSessionError` 和令牌错误；数据库失败不走这一档。

## 3. Access 过期后的登出

`end_login` 只撤销已有登录，不调用 `start_session` 或 `refresh_session`，也不插入新的会话或刷新串。

| 凭证 | 处理 |
| --- | --- |
| Access 仍通过 RS256 校验 | 撤销该 `sid` 的会话、子会话和刷新家族，返回 `revoked` |
| Access 缺失或已过期，Refresh Cookie 对应的刷新串仍未过期 | 按该刷新串的 `family_id` 撤销家族和会话，不轮换、不签发新 access，返回 `revoked` |
| 两张凭证都缺失，或都能识别但都已过期 | 返回 `already_logged_out` |
| 数据库不可用 | 返回存储不可用，不当作已经登出 |

有效 Access 优先。即使同时带了 Refresh Cookie，也不会因此创建新会话。过期 Access 不能定位会话时，才使用 Refresh Cookie。刷新串已过期则不再把它当成一次可执行的登出，也不制造新会话。

## 4. 数据库异常 fail-closed

会话查询和 `last_used_at` 更新遇到 `OperationalError` 或 `ProgrammingError` 时，事务回滚并抛出 `BaseSessionUnavailable`。`session_failure_status` 把这个异常映射为 503，把会话或令牌拒绝映射为 401。它不是路由，也没有接入 ENT。

数据库不可用时，`note_verified_access`、`authorize_access` 和 `end_login` 都失败，不返回已通过签名校验的声明，也不把登出说成已经完成。`last_used_at` 保持旧值，会话不会被延长，也不会只因为签名有效就被接受。

## 5. 测试结果

解释器：`aiproject/.venv313`。没有运行会改业务数据的客户验收脚本，也没有对 `education_service` 执行 DDL。

| 范围 | 结果 |
| --- | --- |
| `test_base_session.py`、`test_base_session_acceptance.py`、`test_base_session_mysql.py` | 19 通过 |
| `test_base_identity.py`、`test_identity_settings.py`、`test_ent_portal_routes.py` | 17 通过 |
| `test_base_jwt.py` | 18 通过 |

合计 54 通过，0 失败。MySQL 8.0.27 临时库并发测试仍通过，临时库已删除。

## 6. 代码修改清单

- `aiproject/app/core/security/base_session.py`：底层撤销、独立撤销、请求授权、登出和 503 映射。
- `aiproject/tests/modules/test_base_session_acceptance.py`：事务、授权、登出和数据库失败测试。

没有修改 ENT 8002、`AuthService`、Cookie、路由注册、`.env`、待执行 DDL 或 64～77 号报告。

## 7. Git 状态

分支：`feature/base02-safe-baseline`。没有 reset、clean、rebase、amend、整目录添加或推送。

| 提交 | Hash | 内容 |
| --- | --- | --- |
| 本轮代码 | `8bac3fe17fc8a3197d7537815812be3f1038f56a` | 底层撤销、请求授权、登出和数据库失败拒绝 |
| 父提交 | `26f47bbb53de25053da23fce94434697e95880ac` | 77 号报告的提交记录 |
| 安全验收代码 | `ae641f0aca42e165f47db013200bd9c86cd571a0` | 仍保留 |
| 第三阶段实现 | `04fd256d31f85083a79b342795793707cf7c1f90` | 仍是祖先 |

未跟踪且未纳入本次提交：71、72、74 号报告，以及 `backend/`、`docs/`、`教育服务_0914/`。64 至 77 号报告没有被覆盖。

## 8. 第四阶段启动条件

本轮不开始第四阶段。下面这些条件都还没有完成：

1. 批准并在维护窗口执行 `003_base_refresh_token.sql`。
2. 批准门户 Origin 和 CSRF 后，再挂载只接受 POST 的刷新和登出。登出调用 `end_login`，刷新调用 `refresh_session`。
3. 改密、重置、停用和角色停用改为在现有事务里调用 `revoke_user_sessions`，并完成隔离测试。
4. 受保护业务路由调用 `authorize_access`，数据库异常使用 `session_failure_status` 返回 503。
5. 单独批准 7 天清理的调度和失败告警。当前没有生产定时任务。
6. 8000 保持 blocked，学生登录保持关闭，ENT 8002 保持 HS256。
7. 服务会话、换票、组织成员和腾讯云部署仍不在本阶段。
