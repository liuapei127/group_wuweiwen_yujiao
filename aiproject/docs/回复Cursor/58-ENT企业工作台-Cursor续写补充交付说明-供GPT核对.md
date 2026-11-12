# 58 ENT 企业工作台 · Cursor 续写补充交付说明（供 GPT 核对）

| 项 | 内容 |
| --- | --- |
| 日期 | 2026-11-12 |
| 背景 | 用户在 GPT 未完成额度中断后，要求 Cursor **按 GPT 原方案继续**（`frontend/` + Vite/React/Ant Design + 门户 8002，**不**迁到 `html/`） |
| 范围边界 | **未改** GPT 写的业务页面源码（`src/pages/*`、`App.tsx`、`auth.tsx` 等）；仅补文档、验收脚本、pytest、Playwright 冒烟 |
| 核对方 | GPT：请对照本清单逐文件检查，并确认与 `setup_ent_portal.py` / `start_ent_portal.py` / RBAC 设计一致 |

---

## 1. 变更文件一览

| 类型 | 路径 | 说明 |
| --- | --- | --- |
| **新增** | `scripts/verify_ent_portal_http.py` | 门户 HTTP 冒烟（8002、登录、context、employee 越权） |
| **新增** | `tests/integration/test_ent_portal_routes.py` | 隔离 ASGI：`/auth/status` 形态、未登录访问 `/portal/context` |
| **新增** | `docs/ENT-企业工作台-开发联调说明.md` | 与 Dify Chatflow 分工、端口、bootstrap、待办 |
| **新增** | `frontend/playwright.config.ts` | Playwright；`webServer` 自动 `npm run dev` |
| **新增** | `frontend/e2e/smoke.spec.ts` | 登录页可见性 + 可选 API status（连不上则 skip） |
| **重写** | `frontend/README.md` | 由原 Vite 模板说明改为 ENT 工作台中文联调手册 |
| **修改** | `frontend/package.json` | 增加脚本 `"test:e2e": "playwright test"` |
| **修改** | `docs/architecture.md` | 「基本布局」增加一行 `frontend/` 指向联调说明 |

**未在本轮触碰（仍属 GPT 交付主体）**

- `frontend/src/**`（除上述 e2e 外）
- `app/modules/auth/**`、`app/modules/portal/**`、`app/ai/assistant/**`
- `scripts/setup_ent_portal.py`、`scripts/start_ent_portal.py`
- `migrations/002_ent_portal_expected.sql`

---

## 2. 新增/修改代码要点（便于逐段核对）

### 2.1 `scripts/verify_ent_portal_http.py`

下面是 **59 号核对时的初稿行为**，已被后续源码替换，不能再当作当前验收标准：

- 凭据缺失仍可能成功退出
- employee 访问 `/auth/users` 接受 401 或 403
- 只统计权限和菜单数量

**当前源码行为（以仓库文件为准）：**

- 默认范围是 `four-role-rbac`，必须按角色找到 admin、employee、manager、team_leader 各一套且密码齐全；缺文件、缺角色、缺密码或重复账号都非零退出。
- `--health-only` 只表示探活，输出 `scope=auth-readiness`，不算 RBAC 通过。
- 核对 login、`/me`、`/portal/context` 的身份一致，并把权限集合、菜单集合与 `ROLE_DEFAULTS` 和 `FEATURES` 做集合比较。
- 有效身份访问受保护接口：有权限为 200，无权限必须为 403。401 只出现在退出后的令牌失效检查，不能当作越权通过。
- **副作用**：成功登录会新增 `ent_auth_session` 与 `ent_auth_audit`。脚本在 finally 中退出已签发令牌，并要求随后 `/me` 返回 401。审计行会保留。脚本不创建或修改客户、成绩等业务记录。

### 2.2 `tests/integration/test_ent_portal_routes.py`

59 号核对时，该文件接受 `401 或 503`，且可信配置下可能碰到生产数据库引擎。

**当前源码行为：** 显式构造 `Settings` 并替换认证与依赖里的 `get_settings`；`get_db` 指向内存 SQLite；生产引擎的 `connect` 被替换成断言失败。`blocked` 匿名访问 `/portal/context` 精确为 503；有效签名的 `trusted_jwt` 匿名访问精确为 401，并检查 `WWW-Authenticate: Bearer`。

### 2.3 `frontend/e2e/smoke.spec.ts` + `playwright.config.ts`

59 号核对时只有两个用例：登录页，以及直连 8002 且失败就 skip。

**当前源码行为：**

- `ui-smoke` 只检查登录页，不把后端未就绪算作联调通过。
- `portal-integration` 经 `baseURL`（默认 `http://127.0.0.1:5173`）访问 `/api/v1/auth/status`，要求 `trusted_jwt` 且 `ready=true`；再按四角色检查菜单、按钮、受限页面、接口 403 和退出后 401。后端错误不 skip。
- `portal-ai` 单独覆盖确认、取消、写入一条和重复确认。
- `trace` 为 `retain-on-failure`，截图为 `only-on-failure`。设置了 `ENT_PORTAL_URL` 时不启动本地 Vite。未设置 `CI` 时可复用本机服务；`CI` 下 `reuseExistingServer` 为 false。

### 2.4 `frontend/package.json` 变更

仅此 diff（脚本节）：

```json
"test:e2e": "playwright test"
```

### 2.5 `docs/architecture.md` 变更

在「基本布局」首条增加：

> `frontend/`：ENT 企业智能工作台（Vite + React + Ant Design），本地联调见 `docs/ENT-企业工作台-开发联调说明.md`。

---

## 3. 本地已执行验证（Cursor 环境）

| 项 | 命令 | 结果 |
| --- | --- | --- |
| 前端生产构建 | `cd frontend && npm run build` | 成功（`tsc -b && vite build`） |
| 新增 pytest | `pytest tests/integration/test_ent_portal_routes.py -q` | **2 passed** |
| 全量 pytest | `pytest tests -q` | **通过**（与补充前同一套，未新增失败） |
| Playwright | `npx playwright install chromium` + `npm run test:e2e` | **未通过**：Chromium 本体约 205MB 已下到缓存，但 **chrome-headless-shell** 多次 `ECONNRESET`/超时，安装失败 → 用例 1 因缺可执行文件失败，用例 2（API）**skipped**。请在网络稳定环境执行 `cd frontend && npx playwright install` 后重跑 `npm run test:e2e` |

**未执行（需 GPT/用户在有 MySQL + bootstrap 的环境补跑）**

- `python scripts/verify_ent_portal_http.py`（需 8002 门户已启动 + credentials 文件）
- 四角色手工 UI + AI 确认写库
- Portal Dify intent 工作流 Key 配置后的 `/assistant` 端到端

---

## 4. 与 GPT 原设计的一致性核对清单（建议 GPT 逐项打勾）

- [ ] 工作台仍使用 **`frontend/`**，Vite 代理 **8002**，与 `start_ent_portal.py` 一致
- [ ] `verify_ent_portal_http.py` 使用的接口路径与 `modules/auth/router.py`、`modules/portal/router.py` 一致
- [ ] employee 越权测 `users:manage` 与 `rbac.py` 中 `users:manage` 权限一致
- [ ] 文档中 **未声称** 已完成云端合并、FastAPI 静态托管、Portal Dify 自动发布
- [ ] Playwright **不替代** GPT 未写完的「四角色 + AI 写入」验收，仅为冒烟补充
- [ ] `test_ent_portal_routes` 在 `blocked` 与 `trusted_jwt` 下对 `/portal/context` 状态码预期合理

---

## 5. GPT 核对时建议阅读顺序

1. 本文件（58）
2. `docs/ENT-企业工作台-开发联调说明.md`
3. `frontend/README.md`
4. `scripts/verify_ent_portal_http.py`（全文约 100 行）
5. `tests/integration/test_ent_portal_routes.py`
6. `frontend/e2e/smoke.spec.ts`、`frontend/playwright.config.ts`
7. 对照 GPT 自写：`app/modules/portal/service.py` 的 `FEATURES` 与 `frontend/src/navigation.tsx` 是否仍一致（Cursor **未改** navigation）

---

## 6. 给 GPT 的返工格式建议

核对后请回复：

1. **一致** / **不一致**（逐文件）
2. 若不一致：文件路径 + 期望行为 + 建议修改（Cursor 或 GPT 二选一）
3. 是否建议在 `00-文件索引与阅读顺序.md` 增加 58 号链

---

## 7. 完整源码路径（复制给 GPT 读仓库）

```
aiproject/scripts/verify_ent_portal_http.py
aiproject/tests/integration/test_ent_portal_routes.py
aiproject/docs/ENT-企业工作台-开发联调说明.md
aiproject/frontend/README.md
aiproject/frontend/package.json
aiproject/frontend/playwright.config.ts
aiproject/frontend/e2e/smoke.spec.ts
aiproject/docs/architecture.md  （仅基本布局首条有增补）
```

本说明即 Cursor 在 GPT 框架上的 **续写补充范围**；GPT 原有前端与门户后端代码请以仓库当前版本为准单独评审。
