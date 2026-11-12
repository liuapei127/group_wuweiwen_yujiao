# 75 BASE 第二阶段员工、学生和管理员身份映射实现与测试报告

日期：2026-11-12  
结果：**BASE 可以只读识别现有员工、学生和管理员。没有签发登录令牌，没有开放学生登录，没有改数据库。**

第一阶段 RS256 核心保留。本阶段没有重写架构，没有接管 8002，没有连接腾讯云，也没有推送。

## 1. 修改前代码结构

修改前 HEAD 是 `90dd057db28a02e2fb5938b98112c33b9bb652b3`。

| 位置 | 修改前 |
| --- | --- |
| 门户登录 | `AuthService.login` 仍调用 `credentials.issue_token`，算法 HS256 |
| 账号读取 | `AuthRepository.account` 查询整行 `sys_user`，其中包含 `password_hash` |
| 角色与权限 | `sys_role`、`ent_auth_role_permission`。认证时要求 `role_status==1`，权限取表内记录与现有权限目录的交集 |
| 用户表投影 | `app/modules/auth/models.py` 的 `accounts` 是完整列投影。学生模块里的 ORM 只映射部分列，没有另建用户表 |
| BASE 令牌 | `base_jwt.py` 只负责 RS256。当时还没有身份解析 |

没有可复用的、且不读取口令哈希的身份解析函数，所以新增了独立模块，并复用现有表对象。

## 2. 实际修改文件

| 文件 | 变化 |
| --- | --- |
| `aiproject/app/core/security/base_identity.py` | 新增。只读解析 |
| `aiproject/tests/modules/test_base_identity.py` | 新增。隔离 SQLite |
| 本报告和索引 | 记录本阶段 |

没有修改 `AuthService.login`、`credentials.py`、RBAC 目录、登录路由、客户管理或 AI 写入。

## 3. sys_user 读取方式

`resolve_identity(db, user_id)` 只按数字主键读取。查询列是 `id`、`username`、`user_type`、`status`、`role_id`，以及角色表的 `role_code`、`role_name`、`status`。

`password_hash` 不在查询列里，结果对象也没有这个字段。`department` 不读取，因此不会被当成组织编号。

## 4. sys_role 关联方式

用 `sys_user.role_id` 左连接 `sys_role.id`。权限再从 `ent_auth_role_permission` 读取，并且只保留现有 RBAC 目录里已经定义的权限名。这与 `AuthService.authenticate` 的交集方式一致。

目录里没有的权限字符串不会变成授权。`user_type` 或 `role_code` 本身也不会补全一套权限。

## 5. 身份识别规则

`user_type` 必须是数据库原值，而且只能是 `employee`、`admin`、`student`。这三项来自第一阶段已经固定的 `USER_TYPES`。

不会根据 `username` 猜测，也不会根据 `role_code` 改写 `user_type`。用户名是 `admin` 但账号类是 `employee` 时，结果仍是 `employee`。

不存在的用户、非正整数编号，都拒绝。

## 6. 身份与角色的区别

账号类看 `user_type`，角色看 `sys_role.role_code`。测试里同时放了：

- `user_type=employee` 且角色为 `manager`
- `user_type=employee` 且角色为 `team_leader`
- `user_type=employee` 且角色为 `admin`
- `user_type=admin` 且角色为 `admin`

后两行角色编码相同，账号类仍然不同。两行都只有表里实际写入并属于权限目录的那一项权限，不是整套管理员权限。

## 7. 账号状态检查

现有登录要求账号 `status=normal` 且 `role_status==1`。64 号没有规定缺角色时可以放行。因此本阶段同样不放行：

| 情况 | 结果代码 |
| --- | --- |
| 用户不存在 | `missing` |
| `status` 不是 `normal`，包括停用员工和停用学生 | `disabled` |
| `user_type` 不是三种原值之一 | `invalid_user_type` |
| `role_id` 为空，或指向不存在的角色 | `missing_role` |
| 角色状态不是 1 | `disabled_role` |

停用账号不会得到可认证身份。学生在账号和角色都正常时可以被识别，但 `ent_login_allowed` 为假。这个标志只重复现有 ENT 的账号类限制，不签发令牌，也不改变登录代码。

## 8. JWT Claims 映射关系

成功结果里的 `sub` 是 `sys_user.id` 的十进制字符串，不含前导零。`user_type` 是数据库原值。

没有 `sid` 字段，不创建 `ent_auth_session`，也不调用 RS256 或 HS256 签发。会话编号留给后续阶段。

## 9. 学生登录隔离情况

隔离 SQLite 上调用了未改动的 `AuthService.login`。学生使用正确密码仍然返回 401，并且没有写入会话。同一夹具里的员工登录仍得到 `alg=HS256`。生产引擎的连接被测试主动禁止。

没有学生登录路由，8000 仍是 blocked。没有创建管理员账号，也没有修改真实用户行。

## 10. ENT 兼容性测试

| 测试 | 结果 |
| --- | --- |
| `test_student_can_be_identified_but_existing_login_rejects` | 学生可识别；现有登录拒绝学生；员工登录仍是 HS256 |
| `test_ent_portal_hs256_remains_unchanged` | 门户签发和验证仍是 HS256 |
| `test_identity_settings.py` | 默认模式仍是 blocked |
| `test_ent_portal_routes.py` | 隔离 SQLite 上的认证路由仍按原状态码工作 |

## 11. 测试执行结果

命令：

`aiproject/.venv313\Scripts\python.exe -m pytest tests/modules/test_base_identity.py tests/modules/test_identity_settings.py tests/integration/test_ent_portal_routes.py tests/modules/test_base_jwt.py::test_ent_portal_hs256_remains_unchanged -q --tb=short`

结果：**18 passed**。其中身份映射 8 项，其余是上面的 ENT 回归。全部使用内存 SQLite 或纯内存密钥，没有连接业务库写入。

要求中的 18 种情况都在身份测试里：

| 要求 | 覆盖 |
| --- | --- |
| 正常员工、管理员、学生 | `test_employee_admin_and_student_are_distinct` |
| 不存在的用户、停用员工、停用学生 | `test_missing_and_disabled_accounts_are_rejected` |
| 非法 user_type | `test_invalid_user_type_is_rejected` |
| 缺少 role_id、角色不存在、角色停用 | `test_missing_role_and_disabled_role_are_rejected` |
| employee 加 manager、team_leader，以及 admin 账号类和 admin 角色的区别 | `test_employee_role_does_not_change_account_class` |
| 学生可识别但不能走现有登录 | `test_student_can_be_identified_but_existing_login_rejects` |
| user_type 不自动授予全部权限 | 管理员与“员工加 admin 角色”都只有表内的一项权限 |
| sub 为十进制字符串 | 上述成功结果中的 `sub` |
| 不读取、不输出 password_hash | 查询列断言，以及结果中不含预置哈希 |
| 不伪造 sid | 结果类型没有 `sid` 字段 |

另外，`test_username_is_not_used_to_guess_identity` 确认用户名不能决定账号类。

## 12. 数据库变更情况

没有。没有 DDL，没有 INSERT、UPDATE、DELETE，没有改口令、账号或授权。测试库是进程内 SQLite，结束即丢弃。

## 13. Git 分支和提交 Hash

分支：`feature/base02-safe-baseline`。

身份解析代码和测试的提交是 `1982dda06f189962028152e4b140b4f43cf0c23e`。父提交是 `90dd057db28a02e2fb5938b98112c33b9bb652b3`。

没有 `reset`、`clean`、`rebase`、`filter-repo`、`amend` 或 `git add .`，也没有推送。71、72、74 号报告以及 `backend/`、仓库根目录 `docs/`、`教育服务_0914/` 仍未纳入本次提交。

## 14. 下一阶段 Refresh Token 和会话管理计划

下一阶段才处理刷新串和会话，不在本阶段实现。按 64 号：

1. 刷新串是 256 位随机值，不是 JWT。库中只保存 SHA-256，并带家族、会话、用户和失效时间。
2. `sid` 使用 `ent_auth_session.id`。给这张表增加 `signing_kid` 之前，先单独提交 DDL、影响范围和回滚方案，等确认后再执行。
3. 登出、停用、改密和密钥停用要撤销对应会话与刷新家族。
4. 仍然不开放学生登录，不把 8002 改成 RS256，不开放 8000。
5. 组织成员和主部门继续后置。`department` 仍只是文本。
