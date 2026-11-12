# 3 · GPT《客户管理 E2E 评审与修复任务》— Cursor 回应（R2）

日期：2026-11-11  
对应文件：`aiproject/docs/客户管理_E2E评审与修复任务.md`

---

## 1. 对 GPT 评审结论的认同

| GPT 观点 | Cursor 采纳 |
| --- | --- |
| 本地基本业务读写有效，但≠权限/HTTP 联调/云端/Dify 验收 | ✅ 已在下文分层标注 |
|「未绕过鉴权」表述不准确 | ✅ 已改认证策略与表述 |
| 仅 2 表未证明与 31 表标准一致 | ✅ 已补结构对比说明（§4） |
| `pip install -e .` 与 Docker 风险 | ✅ 已调 pyproject，待干净环境复验 |
| TestClient ≠ 真实 HTTP | ✅ 已增 `run_customer_http_e2e.py` |
| 403 不应 HTTP 200 | ✅ consultant 业务错误改 HTTPException |
| 不改云端、不扩业务 | ✅ 本轮仅本地 |

---

## 2. 本轮已修复（代码）

| # | 问题 | 改动 |
| --- | --- | --- |
| 1 | 无身份可更新状态 | 新增 `app/core/auth/dependencies.py`：`require_employee` 需 `Authorization: Bearer` + 合法 `X-Employee-Id`；未配置 `AUTH_BEARER_TOKEN` → **503**；无 Bearer → **401** |
| 1b | 权限可省略 | `update_status` **必须** `operator_employee_id`，且须等于 `owner_employee_id` |
| 1c | consultant 全路由 | 录入/查/改/状态/跟进均 `Depends(require_employee)` |
| 6 | HTTP 语义 | 404/403/409/422 使用 **HTTP 状态码**（非 200+code） |
| 3 | pyproject | 去掉缺失 readme 引用；`setuptools` package 发现排除 tests/scripts |
| 5 | 配置 | `.env.example` 增加 `AUTH_BEARER_TOKEN`（仍用 `config.py` 单文件；云端 `config/` 目录待与集成负责人对齐，**未擅自删改**） |

**认证阻塞（如实报告）**：尚无公共 `modules/auth` / JWT。当前仅为 **服务间 Bearer + 员工 ID 头**，仅供本地与 Dify 网关联调前过渡；**不能**视为生产员工登录。

---

## 3. 认证状态说明（交付物 §2）

| 项 | 状态 |
| --- | --- |
| 公共 auth | ❌ 未完成，需集成负责人契约 |
| 当前机制 | `AUTH_BEARER_TOKEN`（.env，gitignore）+ `X-Employee-Id`（Bearer 通过后才读取） |
| 生产绕过开关 | ❌ 未添加 |
| 测试覆盖 | TestClient 脚本需带头；无 token 预期 **401/503** |

---

## 4. 两表与 `db_init.sql` 差异（交付物 §3）

**方法**：对照 `教育服务_0914/2222通过表可以实现curd/db_init.sql` 与本地 `CREATE TABLE IF NOT EXISTS`（E2E 前创建）。

| 对比项 | `db_init.sql` | 本地 E2E 建表 | 风险 |
| --- | --- | --- | --- |
| `crm_lead` 字段集 | 完整字段+COMMENT+索引+`customer_profile_id` | 字段基本一致，**无 COMMENT**，索引略简 | `IF NOT EXISTS` 不改正已存在表 |
| `crm_follow_up` | 含 `idx_employee_id` | 缺 `idx_employee_id` | 查询性能/标准不一致 |
| 字符集 | utf8mb4_unicode_ci | utf8mb4 | 一般兼容 |
| 外键 | 无显式 FK | 无 | 与标准一致 |
| 库内其余 29 表 | 云端标准有 | 本地测试库 **无** | **不能**声称兼容全库 |

**建议（待集成确认后执行）**：在隔离测试库执行经审查的 `db_init.sql`（去掉 DROP 段）或迁云标准库结构；**不在本轮自动执行**。

---

## 5. `pip install`（交付物 §4）

| 阶段 | 结果 |
| --- | --- |
| 修复前 | `pip install -e .` 失败（readme 等 setuptools 问题，见 R1 记录） |
| 修复后 | 已改 `pyproject.toml`；**本轮待在干净 venv 复跑 `pip install .` 并记录输出** |
| Docker build | ❌ 本轮未在本地 Docker 验证 |

---

## 6. config.py vs `config/`（交付物 §5）

| 项 | 说明 |
| --- | --- |
| 本仓库 | 单文件 `app/core/config.py`，变量 `DB_*`、`AUTH_BEARER_TOKEN` |
| 云端骨架 | 可能存在 `app/core/config/` 包结构 |
| 处理 | **未覆盖云端**；合并时由集成负责人决定迁移清单 |

---

## 7. 测试分层（交付物 §5、§6）

| 层级 | 状态 |
| --- | --- |
| 单元（状态机） | `tests/test_lead_status_rules.py` |
| TestClient + MySQL | R1 记录（**历史**）；auth 改造后需 **重跑** |
| HTTP + Uvicorn | 脚本 `scripts/run_customer_http_e2e.py`（需 `AUTH_BEARER_TOKEN`） |
| Dify | ❌ 未做 |
| 云端 | ❌ 未做 |

**R1 历史报告**：`docs/客户管理-E2E验证报告-提交GPT.md` 中「未绕过鉴权」表述 **作废**，以本文为准。

---

## 8. 补充测试清单进度

| 测试 | R2 |
| --- | --- |
| 正常闭环 | 待 auth 配置后 HTTP 脚本重验 |
| 未认证 | 已实现 401/503，待 HTTP 记录 |
| 无权限 | 已实现 403（他人 owner） |
| 非法状态 | 409 ConflictError |
| 不存在 | 404 |
| 跟进写入 | 接口已有，R1 未测写入；可下轮补 |

---

## 9. 报告质量修正（GPT §5）

- 新测试标记使用 **运行时刻** `E2E_HTTP_YYYYMMDD_HHMMSS`，不用伪日期。  
- 共享文档 **不出现完整手机号**（HTTP 脚本日志需二次脱敏后再外发）。  
- 凭据来源：`.env` 本地授权配置，**不**扫描猜测密码。

---

## 10. 给 GPT 的一行结论

R1 证明了 **ORM+MySQL 业务链**；GPT 正确指出 **权限与 HTTP 语义不合格**。R2 已在 consultant 模块加 **默认证拒绝 + Bearer 门槛 + HTTP 状态码**；**公共 auth、31 表标准库、Docker build、Dify/云端** 仍阻塞或待验证；请评审 `app/core/auth/dependencies.py` 与 `consultant/router.py` 是否符合团队认证路线图。

---

## 11. 建议刘培阳下一步

1. 在 `.env` 设置 `AUTH_BEARER_TOKEN`（本地随机串，勿提交）。  
2. 运行：`python scripts/run_customer_http_e2e.py`。  
3. 将输出贴回 GPT，并同步集成负责人 auth 契约。  
4. 不在本地库执行含 DROP 的全量 SQL。
