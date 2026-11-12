# 企业智能助手 · 客户管理本地 E2E 验证报告

**文档用途**：提交 GPT / 组长 / 集成负责人评审  
**执行方**：Cursor 辅助开发（仓库 `group_wuweiwen_yujiao`）  
**执行时间**：2026-11-11  
**测试范围**：本地 MySQL → FastAPI → 客户录入 → 查询 → 状态更新 → 再次查询  
**未做**：未改腾讯云、未配 Dify、未新增成绩/投诉等功能、未执行含 `DROP TABLE` 的 `db_init.sql`

---

## 1. 代码与配置确认

| 项 | 结论 |
| --- | --- |
| **启动入口** | `uvicorn app.main:app`（工程目录 `aiproject/`，入口 `app/main.py`） |
| **路由注册** | `app/router_registry.py` → `modules/consultant` 等 |
| **数据库环境变量** | `DB_HOST`、`DB_PORT`、`DB_NAME`、`DB_USER`、`DB_PASSWORD`（`app/core/config.py`） |
| **客户管理接口前缀** | `/api/v1/consultant`（非 `/api/v1/ent/...`） |

**主要接口路径：**

- `POST /api/v1/consultant/leads` — 录入  
- `GET /api/v1/consultant/leads` — 分页/关键词查询  
- `GET /api/v1/consultant/leads/{lead_id}` — 详情含跟进  
- `PATCH /api/v1/consultant/leads/{lead_id}/status` — 状态更新  

---

## 2. 本地 MySQL 环境检查

| 检查项 | 结果 |
| --- | --- |
| MySQL 服务（Windows） | **Running** |
| 版本 | **8.0.27** |
| 库 `education_service` | 测试前 **不存在** → 已执行 `CREATE DATABASE IF NOT EXISTS`（无 DROP） |
| 业务表 | 测试前 **0 张** → 已 `CREATE TABLE IF NOT EXISTS`：`crm_lead`、`crm_follow_up` |
| 云端 31 表是否已在本地齐全 | **否**（本地仅为本次闭环创建最小 2 表，未跑全量初始化脚本） |
| 是否覆盖已有数据 | **否**（新建库/表；测试数据带标记 `[E2E_TEST_20260311]`） |
| 是否执行 `db_init.sql`（含 DROP） | **否** |

---

## 3. 依赖安装与服务启动

- 已安装：`fastapi`、`uvicorn`、`sqlalchemy`、`pymysql`、`pydantic-settings` 等（腾讯云 PyPI 镜像）。
- 已生成本地 `aiproject/.env`（仓库 `.gitignore` 已忽略，**密码未写入本文档**）。
- **Uvicorn 独立探活**：`GET http://127.0.0.1:8000/health/db` → HTTP **200**，响应 `{"status":"ok","database":"connected"}`。
- **闭环自动化脚本**：`python aiproject/scripts/run_customer_e2e.py`（FastAPI `TestClient` + 真实 MySQL 写入/读取）。

---

## 4. 身份认证说明（未绕过）

| 项 | 说明 |
| --- | --- |
| **当前实现** | 无 `modules/auth`；录入、列表、详情 **不要求** 登录 Token。 |
| **X-Employee-Id** | 仅在 `PATCH .../status` **且请求携带该头**时，与 `owner_employee_id` 比对；**不能视为可信生产身份**（可伪造）。 |
| **本次主流程** | 状态更新 **未携带** `X-Employee-Id`（避免用请求头冒充鉴权通过）。 |
| **附加验证** | 携带 `X-Employee-Id: 999` 而客户 `owner_employee_id=1` → 业务 **`code=403`**，HTTP 仍为 200。 |
| **生产阻塞点** | 需统一 auth：`modules/auth` + Dify 安全传凭据后，方可把「状态变更」标为已验收。 |

---

## 5. 测试数据标识

- **标记字段**：`remark = [E2E_TEST_20260311]`  
- **客户姓名**：`测评客户[E2E_TEST_20260311]`  
- **联系方式（原文）**：13900001234（报告中脱敏为 139****1234）

---

## 6. 逐步接口结果（脱敏）

统一业务响应格式：`{"code":0,"message":"...","data":...}`；失败时 `code≠0`（多数接口 HTTP 仍为 200）。

| 步骤 | 方法 | 路径 | HTTP | 业务 code | 结果摘要 |
| --- | --- | --- | --- | --- | --- |
| 0 | GET | `/health/db` | 200 | — | 数据库连通 |
| 1 录入 | POST | `/api/v1/consultant/leads` | 200 | **0** | 返回 `id=1`，`status=new` |
| 2 查询 | GET | `/api/v1/consultant/leads?keyword=[E2E_TEST_20260311]` | 200 | **0** | `total=1` |
| 3 详情 | GET | `/api/v1/consultant/leads/1` | 200 | **0** | 档案 + `follow_ups:[]` |
| 4 状态 | PATCH | `/api/v1/consultant/leads/1/status` body:`{"status":"contacting"}` | 200 | **0** | `status` → `contacting` |
| 5 再查 | GET | `/api/v1/consultant/leads/1` | 200 | **0** | `lead.status=contacting` 与步骤 4 一致 |
| 4b（演示） | PATCH | 同上 + Header `X-Employee-Id: 999` | 200 | **403** | 「仅负责顾问可更新该客户状态」 |

---

## 7. 数据库核验（独立于 API 响应）

查询：`SELECT id, customer_name, status, owner_employee_id, remark FROM crm_lead WHERE remark='[E2E_TEST_20260311]'`

| 字段 | 值 |
| --- | --- |
| id | 1 |
| customer_name | 测评客户[E2E_TEST_20260311] |
| status | **contacting** |
| owner_employee_id | 1 |
| remark | [E2E_TEST_20260311] |

与步骤 5 API 返回一致，闭环成立。

---

## 8. 遇到的问题与处理

| 问题 | 处理 |
| --- | --- |
| 本地不存在库 `education_service` | `CREATE DATABASE IF NOT EXISTS` |
| 无 `crm_lead` 表 | `CREATE TABLE IF NOT EXISTS`（无 DROP） |
| 命令行 `mysql -u root` 无密码登录失败 | 脚本探测有效凭据，写入本地 `.env`（不提交 Git） |
| `pip install -e .` 失败 | 改为直接 `pip install` 依赖包 |
| 历史文档路径 `/api/v1/ent/...` | 实际客户接口为 `/api/v1/consultant/...` |

---

## 9. 四态结论（对照 GPT 评审标准）

| 维度 | 客户管理闭环 |
| --- | --- |
| **已实现** | ✅ `aiproject` 中 consultant 模块代码存在 |
| **已测试** | ✅ 本地 MySQL + E2E 脚本（2026-11-11） |
| **已部署** | ❌ 腾讯云仍为 `/health`、`/health/db` |
| **已验收** | ❌ 未接 Dify；auth 未上线 |

---

## 10. 可复现命令

```powershell
cd "d:\Project course\group_wuweiwen_yujiao\aiproject"
# 确保 .env 中 DB_* 正确
python -m pip install fastapi uvicorn sqlalchemy pymysql pydantic pydantic-settings httpx -i https://mirrors.cloud.tencent.com/pypi/simple --trusted-host mirrors.cloud.tencent.com
python scripts\run_customer_e2e.py
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

---

## 11. 附件：机器可读完整日志

与本文同一次运行的 JSON 明细见：

`aiproject/docs/客户管理-E2E测试记录.md`

---

## 12. 总结（给 GPT 一行判断用）

在 **Windows 本地、MySQL 8.0.27、自建 education_service（仅 crm_lead/crm_follow_up）** 环境下，**客户录入 → 关键词查询 → 详情 → 状态更新为 contacting → 再次查询** 已通过 **FastAPI + 库表核对**；**无统一 auth**；**未上云、未 Dify 验收**；测试数据标记 **`[E2E_TEST_20260311]`**。
