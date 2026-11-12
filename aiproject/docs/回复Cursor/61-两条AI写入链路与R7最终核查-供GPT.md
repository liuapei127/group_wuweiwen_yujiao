# 61 两条 AI 写入链路与 R7 最终核查（供 GPT）

| 项 | 内容 |
| --- | --- |
| 日期 | 2026-11-12 |
| 范围 | 回答 54 号公开 Chatflow 与 60 号工作台 AI 为什么一个 503、一个能写入；单独说明 R7；补本轮验收。不重写 Dify v3、工作台页面、登录和 RBAC |
| 数据 | 已有 `ENT-AI-E2E-*` 待办全部保留。本轮浏览器复跑新增一条，没有删除任何行 |

---

## 1. 54 号和 60 号是不是同一个工作流

**不是。**

| | 54 号公开企业 Chatflow | 60 号工作台 AI 浏览器测试 |
| --- | --- | --- |
| 用户入口 | Dify 应用「企业智能助手-ENT」预览 / WebApp | 浏览器 `http://127.0.0.1:5173/assistant` |
| Dify 应用形态 | 已发布 Chatflow，发布 ID `105f3a44-ad5a-444f-8e66-98ec696deb69`，32 节点 | 私有 Workflow API：`POST {DIFY_API_URL}/workflows/run`，调用方用户名固定为 `ent-portal-intent` |
| 规范文件 | `docs/dify/ent-workflow-v3-fixed.yml`，由 `scripts/build_ent_chatflow.py` 生成 | `docs/dify/ent-portal-intent-workflow.yml`，由 `scripts/build_portal_intent_workflow.py` 生成 |
| 业务 HTTP 目标 | 节点里写死 `http://host.docker.internal:8000` | 契约里仍写 `host.docker.internal:8000`，但 `call_business` 只取路径，改打 `ASSISTANT_API_URL`（门户为 `http://127.0.0.1:8002`） |
| 员工身份 | 不携带员工 JWT。8000 进程默认 `employee_identity_mode=blocked` | 浏览器登录后的员工 JWT，8002 进程显式 `trusted_jwt` |

公开 Chatflow 自己编排确认和 HTTP。工作台只让私有工作流抽出意图文本，确认、取消和是否调用业务接口由 `AssistantService` 在后端决定。

## 2. 60 号写入待办的真实调用路径

本轮 Playwright `portal-ai` 使用员工角色登录（联调清单中的 `ent_employee`，用户 id **1000008**）。

1. 浏览器 `POST /api/v1/auth/login`。`AuthService.login` 校验密码后调用 `issue_token`：HS256 JWT，声明含 `sub`（员工 id）、`sid`（会话 id）、`iss=ent-portal`、`aud=ent-api`。同时插入 `ent_auth_session`，并写一条 `ent_auth_audit` 登录审计。
2. 浏览器带着 `Authorization: Bearer <该 JWT>` 调用 `POST /api/v1/ai/assistant/conversations/{id}/messages`。
3. `require_employee` 看到 8002 的模式是 `trusted_jwt`，于是 `AuthService.authenticate`：验签、核对会话未撤销、账号状态正常，装成 `EmployeePrincipal`（`employee_id`、权限、学生范围都来自服务端，不来自模型）。
4. 若用户说的不是「确认 / 取消」，`DifyIntentClient.extract` 用**服务端工作流密钥**调私有 Dify。员工 JWT **不会**发给 Dify。
5. `plan()` 把写入收成待确认。确认语由服务端状态机处理，不再问模型。
6. 确认后 `call_business` 用**同一个员工 JWT** 请求 `http://127.0.0.1:8002/api/v1/enterprise/todos`。
7. 这条回环请求再次进入 `require_employee`。待办路由调用 `todo.service.create_todo`：`assignee_id=p.employee_id`，然后 `db.commit()`。

所以：JWT 在登录接口生成；两次业务入口都经过可信 principal；写入经过待办 service 和数据库事务。它用的是 **ENT 门户自己的 trusted_jwt**，不是全组 BASE 已经接到公开 8000 Chatflow 上的统一身份。公开 Dify 仍然没有这个 JWT。

## 3. 为什么 54 号是 503，60 号能写入

54 号 HTTP 节点打到 **8000**。`require_employee` 在 `employee_identity_mode != trusted_jwt` 时直接 `HTTP 503`，文案是「员工可信身份未就绪」。公开工作流没有员工 Bearer，即使带了，8000 默认进程也不会走验签放行。54 号把这 27 条 503 记为 partial-succeeded，不能当成保存成功。

60 号回环打到 **8002**，该进程由 `scripts/start_ent_portal.py` 设为 `trusted_jwt`，并有长度足够的 `AUTH_JWT_SECRET`。同一条创建待办请求因此能通过 principal 检查并提交。

本轮检查 `http://127.0.0.1:8000/health` **连接失败**。所以此刻公开 Chatflow 的探活还会先报网络故障；即便 8000 重新起来，在默认 blocked 下业务写入仍应是 503。这和 8002 能写入不矛盾。

## 4. 数据库证据（只读，未删除）

`todo_item` 中标题以 `ENT-AI-E2E-` 开头的行，负责人都是 **1000008**（联调员工，不是写死的员工 1）：

| id | assignee_id | status | title | create_time |
| --- | --- | --- | --- | --- |
| 78 | 1000008 | pending | ENT-AI-E2E-1794469490638 | 2026-11-12 15:45:04 |
| 79 | 1000008 | pending | ENT-AI-E2E-1794469670466 | 2026-11-12 15:48:08 |
| 80 | 1000008 | pending | ENT-AI-E2E-1794471817586 | 2026-11-12 16:23:51 |
| 81 | 1000008 | pending | ENT-AI-E2E-1794472552248 | 2026-11-12 16:36:09 |

78–80 是本轮开始前已有的记录，仍然在。81 是本轮 `npm run test:e2e` 的 AI 用例新增的一条。该用例断言：确认前 0 条、取消后仍 0 条、确认后恰好 1 条、再发「确认」仍然是 1 条，并能按标题查回。测试结果为通过，所以这一条没有被重复插入。

## 5. R7 待办转派扫描时间

**失败原因（59 号第一次全量：92 passed，1 failed）**  
失败点是 `test_source_todo_reassignment_completion_reopening_and_unassignment` 末尾：同一张来源待办转派、重开、取消再分配后，期望 `notification_log` 里有 **5** 个不重复的 `dedup_key`，实际是 **4**。

**是业务实现问题，不是把预期改成 4 就能解释的测试笔误。**  
`synchronize_source` 在转派时把新版本的 `due_time` 设为当时的 `now_naive()`。旧扫描在同步开始前就固定了截止时间。若同步跨过一秒，新 `due_time` 晚于这个截止时间，本轮 `due_time <= now` 选不中它，通知就少一条。下一次扫描若时钟已越过该 `due_time`，才可能补上，所以全量复跑有时又是 5 条。

**当前实现**  
`reminder_repository.collect_reminders` 在全部来源同步完成之后才取 `now`，再用这个截止时间挑选到期待办。预期仍然是 5，没有改成 4。

**受控时钟**  
`test_scanner_notifies_new_assignment_even_if_sync_crosses_second` 把同步时钟每次加 1 秒，扫描截止时间读同一受控时钟。第一次扫描必须通知版本 1；转派后再扫描必须同时存在版本 1 和版本 2 的通知；第三次不再新增。

本轮没有再改这段业务代码。回归结果：

- 上述两个用例：**2 passed**
- 全量 `pytest tests -q`：**115 passed**，8.21 秒。本次没有出现 59 号那次的 1 failed。59 号的首次失败记录仍然有效，不能用这次全绿替换掉。

## 6. 本轮最终验证

| 项 | 结果 |
| --- | --- |
| 8002 `verify_ent_portal_http.py` | **passed**。证据 `docs/回复Cursor/runs/ent-portal-http-61-2026-11-12.json`。employee 访问 `/api/v1/auth/users` 实际 **403**。四角色退出后 `/me` 为 **401** |
| 四角色菜单与越权 | 含在上述 HTTP 记录中。Playwright 另测了页面菜单、按钮和受限 URL |
| Playwright `npm run test:e2e` | **8 passed**，exit code 0，约 1.1 分钟。含登录页、四角色、匿名 401、AI 确认/取消/写一条/重复确认 |
| 前端 `npm run build` | 通过。产物仍是 `index-CQyIR1Vf.css`、`index-DSY3UVs1.js` |
| 全量 pytest | **115 passed** |
| 8000 探活 | 本轮连接失败，公开 Chatflow 这条链路 **尚未在本轮重新验证** |

没有改 `frontend/src`，没有改已发布 Dify v3，没有改登录和 RBAC 实现。

## 7. 状态划分

**已完成**

- 公开 Dify v3 Chatflow（54 号）与门户私有意图工作流、8002 员工 JWT 工作台，是两条已存在的实现。
- R7 的截止时间已放在同步之后，并有受控时钟回归测试。预期条数仍是 5。

**已验证**

- 本轮：115 项 pytest、两个 R7 用例、8002 四角色 HTTP、Playwright 8 项、前端构建、4 条 `ENT-AI-E2E` 待办仍在且负责人为 1000008。
- 54 号当时的 46 条已发布对话和 27 条 503，仍以 54/55 号证据为准，本轮没有重跑。

**尚未验证**

- 本轮没有重新打开 8000，因此没有在「8000 已启动且仍为 blocked」的条件下再打一条公开 Chatflow 业务请求。
- 公开 Chatflow 接上员工 JWT 之后的真实写入，还没有验收。

**尚未开发**

- 全组 BASE 统一身份接入公开 Dify Chatflow。门户 `trusted_jwt` 不能代替这件事。
- 语音、主管范围、外部通知渠道，仍按 54 号后续入口，本轮未做。

**环境阻塞**

- 当前 `127.0.0.1:8000` 没有进程。要复现 54 号探活或 503 业务调用，需要先按 Dify 用的方式启动 8000，并且不要把该进程改成 trusted_jwt 来假装公开链路已接入身份。
