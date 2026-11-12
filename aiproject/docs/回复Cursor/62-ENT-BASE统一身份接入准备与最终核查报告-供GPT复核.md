# 62 ENT：BASE 统一身份接入准备与最终核查（供 GPT 复核）

日期：2026-11-12  
范围：核对 R7 当前实现和证据边界；按原始配置恢复 8000 并验证公开 Dify 的拒绝边界；调查 BASE 统一身份契约。未改生产认证，未发布新的公开工作流，未把 8000 改成 `trusted_jwt`。

## 1. R7 最终代码核查

当前 `collect_reminders` 先完成两类来源同步，再取扫描截止时间。

```62:66:aiproject/app/modules/todo/reminder_repository.py
    # Synchronization may create a due_time in the next second. Capture the cutoff
    # after all source updates so this batch can notify its new assignments.
    now = now_naive()
    # Lock each due todo, then use a current read and a unique key as final protection.
    stmt = select(todos).where(todos.c.status.in_(["pending", "in_progress"]), todos.c.due_time <= now)
```

调用顺序：

1. 对候选来源调用 `synchronize_source`。
2. 对缺少来源、但仍是进行中的待办再调用 `synchronize_source`。
3. 上述循环结束后才执行 `now = now_naive()`。
4. 再用 `due_time <= now` 选择本轮通知。

转派时的到期时间仍在同步函数内部取得，并写入新版本：

```16:28:aiproject/app/modules/todo/synchronization.py
    now = now_naive()
    if old is None:
        if not active:
            return False
        rid = repo.create(dict(assignee_id=owner, todo_type=kind, title=title, related_type=source_type, related_id=source_id, priority="medium", status="pending", due_time=now, assignment_version=1, source_status=marker, create_time=now, update_time=now))
        if rid is not None:
            return True
        old = repo.todo(source_type, source_id)
    values = {"source_status": marker}
    if active:
        reactivated = old["source_status"] in ("approved", "rejected", "cancelled", "resolved", "closed", "missing", "unassigned")
        if old["assignee_id"] != owner or reactivated:
            values.update(assignee_id=owner, status="pending", completed_time=None, due_time=now, assignment_version=old["assignment_version"] + 1)
```

对应测试在 `tests/integration/test_ent_support.py`：

- `test_source_todo_reassignment_completion_reopening_and_unassignment`  
  末尾仍是 `assert len(keys) == len(set(keys)) == 5`。预期数量没有从 5 降到 4。
- `test_scanner_notifies_new_assignment_even_if_sync_crosses_second`  
  受控时钟从 `2030-01-01 12:00:00` 开始。`synchronization.now_naive` 每次调用加 1 秒并返回新时间；`reminder_repository.now_naive` 读取同一时钟、不再加秒。因此同步过程中的 `due_time` 可以落到下一秒，而扫描截止时间看到的是同步已经推进后的时钟。

该受控用例的三次扫描：

| 扫描 | 条件 | 结果 |
| --- | --- | --- |
| 第一次 | 初始分配 | 只有 `todo:{id}:1:1` |
| 第二次 | 来源负责人改为 2 之后 | 同时存在版本 1 和版本 2 两个去重键 |
| 第三次 | 不改变来源，再扫一次 | `todos_created=0` 且 `system_notifications_created=0` |

原问题是：截止时间若取在同步之前，转派写入的 `due_time` 可能比截止时间晚一秒，本轮 `due_time <= now` 就漏掉新版本。现在截止时间取在全部 `synchronize_source` 之后，同一受控时钟下新版本已经到期，本轮可以发出通知；去重键包含待办 ID、负责人和分配版本，第三次扫描遇到已有键就不再新增。

## 2. R7 修改历史及证据边界

**无法还原修改前 diff。** `aiproject` 在 59 号审查时未被 Git 跟踪。本次对该文件执行 `git log` 没有得到任何提交。没有修改前源码副本，本文不编造补丁。

可以核对的只有文档陈述和文件最后写入时间：

| 证据 | 时间 | 能说明什么 |
| --- | --- | --- |
| 59 号 | 2026-11-12 15:19 | 第一次全量是 92 passed、1 failed。失败是通知期望 5、实际 4。59 号把当时实现描述为“批次开始就固定 now”，并写明该轮没有改这段业务代码 |
| `test_ent_support.py` | 15:31:07 | 文件最后写入时间。不能据此还原写入前内容 |
| `reminder_repository.py` | 15:31:29 | 文件最后写入时间。当前内容已是“同步之后再取 now” |
| `synchronization.py` | 2026-11-11 23:38 | 12 日下午没有再写入。转派时设置 `due_time` 的位置这次没有新的文件写入 |
| 60 号 | 16:28 | 该轮 Cursor 声明没有改 `reminder_repository.py`，并把 R7 记为未处理。它没有附修改前源码 |
| 61 号 | 16:37 | 按当时磁盘上的代码描述了同步后取截止时间，并声明该轮没有再改这段业务代码 |
| 本次 62 号 | — | 没有修改这三个文件 |

因此只能确认：59 号记录的失败和“批次开始固定 now”是当时的审查结论；当前源码已经把截止时间放在同步之后，并带有跨秒回归测试。15:31 的文件写入落在 59 号和 60 号之间，但没有基线，不能把它指定成某一轮的补丁，也不能用 60 号的“未处理”陈述覆盖当前源码。59 号的首次失败记录继续有效。

## 3. 全量 pytest 结果

本次在 `aiproject` 使用 `.venv313` 执行 `python -m pytest -q --tb=no`：

**115 passed in 19.88s**，退出码 0。

这是一次新的全绿结果。它不替换 59 号记录的第一次全量：92 passed、1 failed。

## 4. 8000 与公开 Dify 的实测边界

8000 使用原启动脚本 `scripts/start_api_for_dify.ps1`：监听 `0.0.0.0:8000`，不在脚本里改身份模式。`.env` 中 `EMPLOYEE_IDENTITY_MODE=blocked`。启动前父进程该变量为空；本次子进程显式设为 `blocked`，与 `.env` 一致。没有把 8000 改成 `trusted_jwt`，也没有改 `.env`。

同一时刻 8002 的 `/api/v1/auth/status` 仍是 `mode=trusted_jwt`、`ready=true`。两个端口保持独立。

### 三种故障的区分

| 现象 | 本次结果 | 含义 |
| --- | --- | --- |
| 连接失败 | 61 号当时 8000 连接被拒绝 | 服务没起来，或网络不可达。那不是 503 |
| HTTP 404 | `GET /api/v1/does-not-exist` 返回 404 `Not Found` | 路由不存在。不能当成身份拒绝 |
| HTTP 503 | 见下表，响应正文是“员工可信身份未就绪，consultant 业务不可用” | 服务已启动，业务身份按默认策略拒绝 |

### 本机 8000

| 请求 | 结果 |
| --- | --- |
| `GET /health` | **200** `{"status":"ok"}` |
| `GET /api/v1/auth/status` | **200** `mode=blocked`，`ready=false` |
| `GET /api/v1/consultant/leads`，无身份 | **503** |
| 同一地址加 `X-Employee-Id: 1000008` | **503** |
| 同一地址加 `Authorization: Bearer forged.not.a.jwt` | **503** |
| `GET /api/v1/portal/health`，无身份 | **503** |
| `POST /api/v1/consultant/leads`，同时带伪造员工头、伪造 Bearer，以及 `owner_employee_id=1000008` | **503** |

写入前后只读计数：`crm_lead` 31→31，`todo_item` 21→21。伪造身份没有新增业务记录。

### 从 Dify 运行环境访问

`dify-api-1` 直接访问 `http://host.docker.internal:8000/health` 为 **200** `{"status":"ok"}`。同一容器访问 `/api/v1/consultant/leads` 为 **503**，正文仍是员工身份未就绪。

再经 `http://ssrf_proxy:3128` 访问：探活 **200**；带伪造员工头和伪造 Bearer 的客户列表请求仍是 **503**。容器进程环境里没有看到 `SSRF_PROXY`、`HTTP_PROXY` 或 `HTTPS_PROXY`；上面的代理结果是显式把请求交给 `ssrf_proxy:3128` 得到的。公开 Chatflow 没有在本次重新发布，也没有重跑 54 号的 46 条对话。

8000 进程保持运行。公开 Dify 现在能到达业务 API，但业务请求仍因身份未就绪返回 503，不是连接失败。

## 5. BASE 统一身份：调查结果与仍缺的契约

仓库和组会记录里没有 BASE 已确认的接口契约。`docs/组会纪要-2026-11-11.md` 写明统一 JWT 未合入。`docs/回复Cursor/04-认证阻塞项与契约待决.md` 的签发方、audience、算法、JWKS、员工映射、撤销和 Dify 代理规则，实际确认栏都是未确认。本次没有找到 JWKS 地址、公钥、测试账号或 BASE 签发示例，因此下面各项都不编造具体值。

8002 现有 JWT 不是 BASE 身份。它由 ENT `issue_token` 用本机密钥签 HS256，claims 为 `sub`、`sid`、`iat`、`nbf`、`exp`、`iss=ent-portal`、`aud=ent-api`、`typ=access`。这只说明门户自己的 trusted_jwt 已可用，不能记成 BASE 统一认证已完成。

| 需要核实的项 | 当前结论 |
| --- | --- |
| BASE 接口和认证方式 | 未提供。没有可调用的登录、换票或校验地址 |
| 签发方、算法、有效期 | 未提供 |
| issuer、audience、claims | 未提供 |
| 公钥、JWKS 或密钥获取 | 未提供。不能把 ENT 门户密钥当成 BASE 密钥 |
| 员工、角色、组织、数据权限映射 | 未提供。不能假设 `sub` 一定等于 `sys_user.id` |
| 过期、撤销、无效员工 | 未提供。401 还是 403 仍是 04 号待决项 |
| 8000 如何验 BASE 身份 | 契约到达后，应由 8000 验签并只信任验签结果；验签失败继续拒绝。现在保持 `blocked` |
| 公开 Dify 如何传递身份 | 尚未有模型不可改写的传递通道。不能把 JWT 或密钥放进提示词，也不能信任对话变量里的 `employee_id` |
| 防止模型指定员工 | 员工 ID 必须来自服务端验签，不来自模型输出、普通变量或客户端头 |
| 写入仍走原业务层 | 身份通过后，仍应进入现有 router、service、权限检查和原事务。本次没有改这条路径 |

在其他模块提供下列材料之前，不改 `app.main` 的默认拒绝，不发布新的公开工作流：

1. BASE 登录或换票接口、测试账号，以及一张可验签的示例令牌。
2. 算法、issuer、audience、有效期、时钟偏差、JWKS 或公钥的获取与轮换方式。
3. 员工 ID、角色、组织和数据范围各使用哪个 claim，以及停用员工、过期令牌、撤销令牌分别返回什么。
4. 公开 Dify 的浏览器用户如何取得 BASE 令牌，以及 HTTP 节点用哪一个模型改不了的凭据位置把它传给 8000。
5. 调用是否必须经过网关；若经过网关，网关签名覆盖哪些字段，以及直连 8000 是否禁止。

## 6. 状态

**已完成**

- R7 当前实现和受控时钟用例已按源码核对，预期通知数仍是 5。
- 8000 已按 blocked 原配置启动，并与 8002 的 trusted_jwt 分开。

**已验证**

- 全量 pytest：115 passed，19.88 秒。
- 8000 `/health` 为 200；无身份和伪造身份的业务请求为 503；404 与 503 已分开；`crm_lead`、`todo_item` 计数未增加。
- `dify-api-1` 能直接以及经 `ssrf_proxy:3128` 到达 `host.docker.internal:8000`。

**尚未验证**

- 没有修改前源码，R7 的历史 diff 无法验证。
- 没有重跑 54 号已发布 Chatflow 的 46 条对话。
- BASE 令牌的验签、过期、撤销和真实员工写入都还没有可执行用例。

**尚未开发**

- 8000 对 BASE JWT 的验签接入。
- 公开 Dify 上模型不可伪造的员工身份传递。
- 公开 Chatflow 的真实员工业务写入。

**环境阻塞**

- 本次 8000 和 Dify 容器网络没有阻塞。
- BASE 契约、测试账号和密钥配置缺失，阻塞的是身份接入，不是本次探活。

## 7. 本轮没有做的事

没有修改登录、RBAC、`frontend/src`、已发布 Dify v3、`reminder_repository.py` 或 `synchronization.py`。没有用固定员工编号写业务数据，没有取消 8000 的默认拒绝，也没有把 8002 的 trusted_jwt 写成 BASE 已接入。
