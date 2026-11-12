# 代码审查结论：统一鉴权收口任务（给 Cursor）

> 审查日期：2026-11-11
> 审查范围：`aiproject/app/` 全量
> 目标：让所有员工业务接口在公共 auth 落地前，统一被 503 锁住；auth 落地后统一放行。

---

## 一、当前现状（已核实）

### 1.1 已经做对的部分

| 项 | 位置 | 状态 |
|---|---|---|
| 身份模式开关 | `app/core/config.py` `employee_identity_mode`，默认 `blocked` | ✅ |
| 启动时校验 mode | `app/main.py` 非 `blocked`/`trusted_jwt` 直接 RuntimeError | ✅ |
| `require_employee()` 依赖 | `app/core/auth/dependencies.py`，任何模式都抛 503 | ✅ |
| consultant 路由全部接入鉴权 | `app/modules/consultant/router.py` 6 个接口都 `Depends(require_employee)` | ✅ |
| 健康检查 | `app/modules/system/router.py` `/health`、`/health/db`，无需鉴权 | ✅ |
| NL2SQL 白名单 | `app/ai/nl2sql/security.py`，禁 raw SQL、只允许白名单 intent | ✅ |
| Python 3.13 | `Dockerfile`、`pyproject.toml` | ✅ |

### 1.2 发现的问题（本次要修）

**问题：只有 consultant 模块被 503 保护，其余四个业务模块生产环境裸奔。**

| 模块 | 路由前缀 | 文件 | 现状 |
|---|---|---|---|
| 员工日报 | `/api/v1/employee-reports` | `modules/employee_report/router.py` | 无任何鉴权，任何人可 POST/GET |
| 学生行政（请假审批） | `/api/v1/student-admin` | `modules/student_admin/router.py` | 只从 Header 读 `X-Employee-Id`，无 blocked 拦截 |
| 企业统一指令 | `/api/v1/enterprise` | `modules/enterprise_ops/router.py` | 只从 Header 读 `X-Employee-Id`，无 blocked 拦截 |
| NL2SQL | `/api/v1/ai/nl2sql` | `app/ai/nl2sql/router.py` | 只从 Header 读 `X-Employee-Id`，无 blocked 拦截 |

**后果**：公网一旦暴露，任何人不登录就能写日报、批请假、查数据、调指令。

### 1.3 附带的两个小问题

1. `dependencies.py` 里 `trusted_jwt` 分支也是 503（第 20-21 行），等于 trusted_jwt 根本没实现。
2. `config.py` 定义了 `auth_bearer_token`，但全项目没有任何 router 读它。

---

## 二、本次任务（请 Cursor 执行）

### 任务 1：四个模块统一接入 `require_employee`

**目标**：在公共 auth 契约落地前，把 `employee_report`、`student_admin`、`enterprise_ops`、`ai/nl2sql` 四个模块的所有写操作接口都加上 `require_employee` 依赖，使其在 blocked 模式下返回 503，与 consultant 行为一致。

**具体改动**：

#### 1.1 `app/modules/employee_report/router.py`
- `POST ""`（提交日报 ENT-04）：加 `principal: EmployeePrincipal = Depends(require_employee)`
- `GET ""`（查日报 ENT-05）：加 `principal: EmployeePrincipal = Depends(require_employee)`
- 入参里如果将来要按人过滤，`employee_id` 默认取 `principal.employee_id`，不允许前端传别人的 id（当前先保留入参，但 blocked 模式下直接 503，不影响）。

#### 1.2 `app/modules/student_admin/router.py`
- `GET /leaves/pending`：加 `require_employee`
- `POST /leaves/{leave_id}/approve`：加 `require_employee`
- 删掉 `x_employee_id: Header(...)` 这个入参（trusted_jwt 落地后从 token 取）。

#### 1.3 `app/modules/enterprise_ops/router.py`
- `POST /commands`：加 `require_employee`
- 删掉 `x_employee_id: Header(...)` 入参；service 层调用时的 `approver_id` 等参数从 `principal.employee_id` 派生。

#### 1.4 `app/ai/nl2sql/router.py`
- `POST /query`：加 `require_employee`
- 删掉 `x_employee_id: Header(...)` 入参；service 层调用时 `actor_employee_id` 传 `principal.employee_id`。

**统一 import**：
```python
from app.core.auth import EmployeePrincipal, require_employee
```

### 任务 2：健康检查保持开放

`/health`、`/health/db` **不要**加鉴权，否则 Dify 探活会挂。

### 任务 3：不要动的东西

- `app/core/auth/dependencies.py` 里的 503 逻辑暂时不改（公共 auth 落地时再改 trusted_jwt 分支）。
- `tests/repro/` 演习场不要动（那是故意用 insecure_header 测权限隔离的）。
- consultant 模块不要动（已经是对的）。
- Dockerfile、pyproject.toml 不要动。

---

## 三、验收标准

改完后，本地起服务跑：

```powershell
cd aiproject
.\.venv313\Scripts\Activate.ps1
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

然后用 curl 或 Swagger 验证：

| 接口 | 期望返回 |
|---|---|
| `GET /health` | 200 `{"status":"ok"}` |
| `GET /health/db` | 200（数据库连着的话） |
| `POST /api/v1/consultant/leads` | **503** |
| `POST /api/v1/employee-reports` | **503**（改前是 200/422） |
| `GET /api/v1/employee-reports` | **503** |
| `GET /api/v1/student-admin/leaves/pending` | **503** |
| `POST /api/v1/student-admin/leaves/1/approve` | **503** |
| `POST /api/v1/enterprise/commands` | **503** |
| `POST /api/v1/ai/nl2sql/query` | **503** |

跑现有测试：
```powershell
pytest tests/ -v
```
必须全绿。

---

## 四、改完不用做的事

- 不用实现 JWT 验签（那是公共 auth 负责人的活）。
- 不用改数据库表结构。
- 不用动 Dify 工作流（等 auth 落地后再带 Authorization 头）。

---

## 五、背景一句话

现在 consultant 被锁住了，其他四个模块没锁，等于锁了门但窗户大开。本次任务就是把窗户也钉上，等公共 auth 来了再统一开门。
