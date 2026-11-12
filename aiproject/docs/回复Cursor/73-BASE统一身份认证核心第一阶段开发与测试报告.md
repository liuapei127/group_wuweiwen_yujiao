# 73 BASE 统一身份认证核心第一阶段开发与测试报告

日期：2026-11-12  
结果：**RS256 签发、只接受 RS256 的验证，以及只含公钥的 JWKS 已在独立代码中实现并通过测试。现有 ENT 8002 登录仍使用 HS256。没有连接腾讯云，没有改数据库。**

本阶段依据已复核的 64 号最终架构，没有重写方案。8000 仍由 `EMPLOYEE_IDENTITY_MODE=blocked` 拒绝员工业务。换票、刷新、会话撤销和五个模块接入都还没做。

## 1. 修改前代码结构

修改前 HEAD 是 `8e894577889f0c5fdf60e1cba24e0b9b084ab08c`。当时没有 BASE RS256 模块。

| 位置 | 修改前的事实 |
| --- | --- |
| 启动入口 | `aiproject/app/main.py`。只接受 `blocked` 和 `trusted_jwt` |
| 路由装配 | `aiproject/app/router_registry.py` |
| 门户 JWT | `aiproject/app/core/security/credentials.py` 的 `issue_token` / `decode_token`，算法固定 HS256，`iss=ent-portal`，`aud=ent-api`，payload `typ=access` |
| AuthService | `aiproject/app/modules/auth/service.py`。登录仍走这层 |
| 登录路由 | `aiproject/app/modules/auth/router.py`，前缀 `/api/v1/auth` |
| RBAC | `aiproject/app/core/security/rbac.py`、`authorization.py`、`dependencies.py` |
| 账号与组织表 | `sys_user`、`sys_role`、`sys_organization`、`ent_auth_session` 仍由现有 ENT 使用。本阶段没有查询或修改它们 |
| 依赖 | `pyproject.toml` 已有 PyJWT，没有 `cryptography`，因此当时签不了 RS256 |
| 测试 | `aiproject/tests/modules/` 里是门户和身份模式测试，没有 BASE JWT 测试 |

## 2. 实际修改文件

| 文件 | 变化 |
| --- | --- |
| `aiproject/app/core/security/base_jwt.py` | 新增。签发、验证、密钥集和 JWKS 文档 |
| `aiproject/app/core/security/jwks_router.py` | 新增。`GET /api/v1/auth/jwks` |
| `aiproject/app/router_registry.py` | 只多挂上面的公钥路由 |
| `aiproject/pyproject.toml` | 增加 `cryptography>=43,<47` |
| `aiproject/.env.example` | 增加 `BASE_JWT_KEYS_FILE` 的说明，没有私钥 |
| `aiproject/tests/modules/test_base_jwt.py` | 新增测试 |
| 本报告和 `00-文件索引与阅读顺序.md` | 记录本阶段 |

没有修改 `credentials.py`、`AuthService`、登录路由、RBAC、客户管理或 AI 写入。

## 3. RS256 签发

`issue_access_token` 和 `issue_service_token` 只使用状态为 `active` 的那一把私钥，并显式传入 `algorithm="RS256"`。Header 固定为 `typ=JWT`、`alg=RS256`、`kid`。同时只允许一把 `active` 密钥；`verify_only` 不能签发。

access 最长 3600 秒。服务令牌同样不超过 3600 秒。本阶段没有登录接口调用这两个函数，所以现有 8002 登录不会改用 RS256。

## 4. JWT 验证

`verify_token` 的密码学调用固定为 `algorithms=["RS256"]`。它不根据令牌里的 `alg` 在 HMAC 和 RSA 之间切换。Header 里的 `alg` 只用来拒绝不是 RS256 的令牌，`alg=none` 和 HS256 都在验签前拒绝。

随后核对签名、`iss=edu-base`、调用方给出的单一 `aud`、`exp`、`nbf`、`kid` 和 `token_use`。未知或停用的 `kid` 拒绝。access 必须带 `employee`、`admin` 或 `student`；服务令牌带了 `user_type` 就拒绝。这里的 `student` 只是 64 号声明表里的取值，没有打开学生登录。

## 5. JWKS 接口

`GET /api/v1/auth/jwks` 返回标准 `{"keys":[...]}`。`active` 和 `verify_only` 的公钥都发布，`disabled` 不发布。响应带 `Cache-Control: public, max-age=60`。

没有可用公钥时返回 503，正文是 `{"detail":"BASE 公钥未就绪"}`，并使用 `Cache-Control: no-store`。这不是一张空的公钥名单。JWK 只保留公钥字段，并去掉 `d`、`p`、`q`、`dp`、`dq`、`qi`、`oth`。

## 6. Claims 设计

按 64 号最终复核版第 4 节：

| 字段 | access | service_access |
| --- | --- | --- |
| Header | `typ=JWT`，`alg=RS256`，`kid` | 同左 |
| `iss` | `edu-base` | `edu-base` |
| `aud` | `edu-api:ent`、`edu-api:pf`、`edu-api:cs`、`edu-api:stu`、`edu-api:rpt` 之一 | 上述资源受众之一。技术细节文件里的 `edu-auth:token-exchange` 只保留给以后的换票，本阶段没有换票路由 |
| `sub` | 不含前导零的十进制 `sys_user.id` | `svc:` 加客户端编号 |
| `sid` | 36 位小写 UUID | 同左 |
| `user_type` | `employee`、`admin`、`student` | 不出现 |
| `token_use` | `access` | `service_access` |
| `iat` / `nbf` / `exp` | 签发时 `iat=nbf`，寿命 1 到 3600 秒 | 同左 |

`ent-api` 不会被当成 `edu-api:ent`。

## 7. 密钥配置方式

运行时只读 `BASE_JWT_KEYS_FILE` 指向的仓库外文件，或读环境变量 `BASE_JWT_KEYS`。两者都没有时，`load_keyset()` 抛出配置错误，JWKS 返回 503。

配置是 JSON 数组，字段为 `kid`、`status`、`public_pem`；只有 `active` 可以带 `private_pem`。`verify_only` 和 `disabled` 如果带了私钥，整份配置拒绝。公钥和私钥必须成对，RSA 至少 2048 位。

测试在内存里生成临时 RSA 密钥，不写文件，不写入 Git，也不生成生产密钥。`.env` 没有改。

## 8. 测试用例及执行结果

命令：

`aiproject/.venv313\Scripts\python.exe -m pytest tests/modules/test_base_jwt.py tests/modules/test_identity_settings.py -q --tb=short`

结果：**16 passed**。其中 14 项是新的 BASE 测试，2 项是原有身份模式测试。没有连接业务数据库，没有运行客户 E2E。

| 要求 | 测试 | 结果 |
| --- | --- | --- |
| 正常 RS256 | `test_valid_rs256_token` | 通过 |
| 错误签名 | `test_bad_signature_is_rejected` | 通过 |
| 错误 issuer | `test_wrong_issuer_is_rejected` | 通过 |
| 错误 audience | `test_wrong_audience_is_rejected` | 通过 |
| 过期 | `test_expired_token_is_rejected` | 通过 |
| 尚未生效 | `test_not_yet_valid_token_is_rejected` | 通过 |
| 无效 kid | `test_unknown_and_disabled_kid_are_rejected` | 通过 |
| HS256 拒绝，另含 `alg=none` | `test_hs256_token_is_rejected` | 通过 |
| 错误 token_use | `test_wrong_token_use_is_rejected` | 通过 |
| JWKS 无私钥 | `test_jwks_contains_only_public_material` | 通过 |
| 缺配置安全失败 | `test_missing_key_config_fails_closed` | 通过 |
| 多 kid | `test_multiple_kids_verify_and_rotate` | 通过 |

另外，`test_service_token_omits_user_type` 确认服务令牌没有 `user_type`。`test_ent_portal_hs256_remains_unchanged` 确认旧门户仍签发 HS256，且 BASE 验证器拒绝这张旧令牌。

## 9. ENT 兼容性检查

- `credentials.py` 的签发和验证没有改，测试仍得到 `alg=HS256`、`iss=ent-portal`、`aud=ent-api`、payload `typ=access`。
- `AuthService`、登录路由、RBAC 和客户、AI 写入没有改。
- 新路由只是公钥发布。它不调用 `AuthService`，也不改变 `require_employee`。
- `test_default_employee_identity_mode_is_blocked` 和 `test_main_rejects_unknown_employee_identity_mode` 通过。8000 继续 blocked。

## 10. 数据库变更情况

没有。没有 DDL，没有改 `DB_PASSWORD`、MySQL root 口令、账号或授权，也没有重置数据库。

## 11. Git 分支和提交 Hash

分支：`feature/base02-safe-baseline`。

本阶段代码和本报告的提交 Hash 记在本节下一行。提交前的父提交是 `8e894577889f0c5fdf60e1cba24e0b9b084ab08c`。

`PHASE1_COMMIT`

没有执行 `reset --hard`、`clean`、`rebase`、`filter-repo`、`commit --amend`，没有 `git add .`，没有推送。`backend/`、仓库根目录 `docs/`、`教育服务_0914/` 仍未纳入本次提交。71 号和 72 号报告仍留在工作区，没有被覆盖。

## 12. 下一阶段开发计划

第二阶段只做员工、学生和管理员身份，仍然不替换 8002 的 HS256 登录，也不开放 8000。开始前如果需要新表或新列，先单独提交 DDL、影响范围和回滚方案，等确认后再动数据库。

其后顺序不变：刷新与会话撤销、服务身份、组织成员和主部门、五个模块接入、Dify 身份传递、统一验收。五个模块合并并验收之后，才恢复腾讯云部署。
