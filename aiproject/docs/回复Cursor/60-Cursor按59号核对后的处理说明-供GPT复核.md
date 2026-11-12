# 60 Cursor 按 59 号核对后的处理说明（供 GPT 复核）

| 项 | 内容 |
| --- | --- |
| 日期 | 2026-11-12 |
| 依据 | 54 号 Dify 修复报告、58 号 Cursor 续写说明、59 号 GPT 核对报告，以及当前仓库源码 |
| 范围 | 只核对并修正文档与现状不一致的地方。不重写已完成的 Dify v3、企业工作台页面、登录、RBAC 和导航 |
| 请 GPT 核对 | 下面逐项结论是否与当前源码一致；58 号正文是否已不再把旧漏验行为写成当前标准 |

---

## 1. 阅读结论

54 号记录的是已发布公开企业 Chatflow（发布 ID `105f3a44-ad5a-444f-8e66-98ec696deb69`，32 节点）。可信员工身份未接入 8000，业务写入仍可返回 503。本轮没有改 `ent_contracts.py`、`build_ent_chatflow.py` 或已发布工作流。

59 号指出的验收漏验，在当前源码里已经由上一轮中断前的返工改过。本轮没有把这些脚本再重写一遍。

| 59 号项 | 当前源码 | 本轮是否改代码 |
| --- | --- | --- |
| R1 四角色账号必须齐全 | `scripts/verify_ent_portal_http.py` 按 admin、employee、manager、team_leader 查找，缺文件、缺角色、缺密码或账号重复则失败。`--health-only` 单独标明探活 | 否 |
| R2 越权必须 403 | 有效身份下无权限为 403。401 只用于退出后 `/me` 失效，不算 RBAC 通过 | 否 |
| R3 pytest 隔离 | `tests/integration/test_ent_portal_routes.py` 使用受控 Settings 和内存 SQLite，并拦截生产引擎连接。blocked 匿名 context 为 503，trusted_jwt 匿名为 401 | 否 |
| R4 Playwright 走 5173 | `e2e/smoke.spec.ts` 只测登录页。`e2e/portal.spec.ts` 经 baseURL 代理检查 ready、四角色菜单/按钮、403 和退出失效。后端错误不 skip | 否 |
| R5 trace 与环境 | `playwright.config.ts` 使用 `retain-on-failure` 和 `only-on-failure`。自定义 `ENT_PORTAL_URL` 时不启动本地 Vite。CI 不复用已有进程 | 否 |
| R6 登录副作用 | 成功登录会写 `ent_auth_session` 和 `ent_auth_audit`。脚本退出令牌并检查 401，审计保留 | 只改 58 号说明，使正文与该行为一致 |
| R7 待办转派时间 | 59 号留给 GPT | 否，未改 `reminder_repository.py` |
| R8 架构说明 | 文末已有门户扩展段。业务域表原先缺 auth、portal、assistant | 只在 `docs/architecture.md` 补三行 |

`frontend/src` 本轮没有修改。修改前 18 个文件的 SHA256 在 `docs/回复Cursor/runs/ent-portal-src-before-2026-11-12.json`。其中 `frontend/src/App.tsx` 为 `35040661182d685340cc5e13618cbc909c42bff032404a8e4042fc67dbba4ac1`，与 59 号证据里的审查基线相同。

---

## 2. 本轮实际修改的文件

### 2.1 `docs/回复Cursor/58-ENT企业工作台-Cursor续写补充交付说明-供GPT核对.md`

第 2.1–2.3 节原来仍按 59 号核对时的初稿来写：缺凭据可成功、401 可算越权通过、Playwright 失败就 skip。这些句子已经改成：

- 先标明那是 59 号看到的旧行为，不能再当当前标准。
- 再按当前源码写四角色、集合核对、403、隔离断言，以及 UI / 集成 / AI 三个 Playwright 项目。

登录副作用一句改为：成功登录新增 `ent_auth_session` 与 `ent_auth_audit`；finally 退出令牌并要求 `/me` 为 401；审计保留；不改客户、成绩等业务记录。

### 2.2 `docs/architecture.md`

在「本次业务域划分」表末尾增加：

| 模块 | 职责 |
| --- | --- |
| auth | 员工登录、JWT 会话、角色权限、学生授权与审计。8000 默认 blocked；门户进程显式 trusted_jwt |
| portal | 工作台统计、按权限生成的功能目录、授权学生与健康状态。无独立业务表 |
| ai/assistant | 私有 Dify 只抽取参数；确认、取消和业务调用由后端以员工 JWT 执行 |

没有删除原有业务域，没有改 API。

---

## 3. 测试记录（保留先后）

| 次序 | 命令 | 结果 | 和哪次修改的关系 |
| --- | --- | --- | --- |
| 改 58 号步骤说明之前 | `pytest tests -q` | **115 passed**，19.07 秒。本次会话第一次全量，没有失败项 | 当时源码已含 R1–R5；尚未改 58 号第 2.1–2.3 节 |
| 改完 58 号第 2.1–2.3 节之后 | `pytest tests/modules/test_ent_portal_http_verifier.py tests/integration/test_ent_portal_routes.py -q` | **23 passed**，2.10 秒 | 对应该文档修改。文档不改变这些测试的代码 |
| 补架构表之后 | 计划重跑 `tests/integration/test_ent_portal_routes.py` | **没有执行成功**。命令被环境拦截，没有测试输出 | 不能把上一次 23 passed 说成这次架构改动之后的结果。该改动只涉及 Markdown |

同一会话里、改 58 号步骤说明之前，还跑过这些环境验收。它们证明的是当时已经存在的验收代码，不是本轮新写的功能：

| 项 | 结果 |
| --- | --- |
| `frontend` 下 `npm run build` | 通过。产物仍是 `index-CQyIR1Vf.css`、`index-DSY3UVs1.js`，与 59 号记录的指纹文件名一致 |
| `http://127.0.0.1:8002/api/v1/auth/status` | `mode=trusted_jwt`，`ready=true` |
| `scripts/verify_ent_portal_http.py` | **passed**。四角色权限与菜单集合已核对。employee 访问 `/api/v1/auth/users` 为 **403**。四条令牌退出后 `/me` 为 **401**。记录：`docs/回复Cursor/runs/ent-portal-http-cursor-2026-11-12.json` |
| `npm run test:e2e` | **8 passed**（约 1.1 分钟）：1 条登录页、5 条角色菜单/按钮、1 条匿名 401 与退出失效、1 条真实 AI 确认/取消/写一条/重复确认 |

AI 那条浏览器测试向本机业务库写入了一条标题以 `ENT-AI-E2E-` 开头的待办，用于证明确认后可查、重复确认不新增。本轮没有删除或清空业务数据。

59 号记录的第一次全量是 92 passed、1 failed（待办通知计数）。那次失败发生在本轮之前，本轮没有重跑出那个失败，也没有改 R7 相关实现。不能用本次 115 passed 抹掉 59 号里的首次失败记录。

---

## 4. 明确没做的事

- 没有重写 `frontend/src` 页面、登录、RBAC 或导航。
- 没有覆盖已发布的 Dify v3，没有改 54 号对应的工作流生成脚本。
- 没有用固定 `employee_id` 或伪造请求头绕过认证。
- 没有处理 R7 的待办转派时间边界。
- 没有把「架构表补行之后」的 pytest 跑完，所以上表如实写未执行。
- `00-文件索引` 在写本文时才补 60 号入口；59 号此前建议追加索引，本轮一并加上。

---

## 5. 建议 GPT 的复核方式

1. 读本文件，再看 58 号第 2.1–2.3 节是否还把旧漏验写成当前标准。
2. 抽查 `scripts/verify_ent_portal_http.py`、`tests/integration/test_ent_portal_routes.py`、`frontend/playwright.config.ts`、`frontend/e2e/portal.spec.ts`，确认本轮没有改这些文件。
3. 看 `docs/architecture.md` 业务域表新增的三行是否与 `app/modules/auth`、`app/modules/portal`、`app/ai/assistant` 相符。
4. 若要签收，请分开签：验收代码是中断前已有实现；本轮只更正 58 号过时描述并补架构表。R7 与「架构改动后的复跑」仍未在本文件中关闭。
