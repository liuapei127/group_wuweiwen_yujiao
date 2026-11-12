# 企业智能助手 · 本地迁移清单 & 接口状态

## 一、`backend/` → `aiproject/` 映射（保留逻辑，调整结构）

| 旧路径（`backend/app`） | 新路径（`aiproject/app`） | 说明 |
| --- | --- | --- |
| `routers/health.py` | `modules/system/router.py` | 对齐云端 `/health`、`/health/db` 响应格式 |
| `routers/crm_leads.py` | `modules/consultant/router.py` | 前缀改为 `/api/v1/consultant` |
| `routers/enterprise.py`（跟进/状态） | `modules/consultant/*` | 拆入 repository/service |
| `models/employee_daily_report.py` | `modules/employee_report/models.py` | 独立模块 |
| `routers/student_leaves.py`（审批） | `modules/student_admin/router.py` | 前缀 `/api/v1/student-admin` |
| `services/enterprise_service.py`（nl2sql） | `ai/nl2sql/*` | 白名单 + 禁止 raw SQL |
| `enterprise commands` | `modules/enterprise_ops/router.py` | 写操作专用 |
| `core/config.py`（MYSQL_*） | `core/config.py`（**DB_***） | 与 compose 一致 |
| `routers/courses_events.py` | — | **未迁移**（属客服 CS，非 ENT） |

旧 `backend/` 暂保留作参考，**以 `aiproject/` 为唯一交付目录**。

## 二、已实现接口（本地代码，云端待合并 build 后生效）

| 完整路径 | 方法 | 任务卡 | 状态 |
| --- | --- | --- | --- |
| `/health` | GET | BASE | 与云端一致 |
| `/health/db` | GET | BASE | 与云端一致 |
| `/api/v1/consultant/leads` | POST | ENT-01 | **本地已实现** |
| `/api/v1/consultant/leads` | GET | ENT-02 | **本地已实现** |
| `/api/v1/consultant/leads/{id}` | GET | ENT-02 | **本地已实现** |
| `/api/v1/consultant/leads/{id}/follow-ups` | POST | ENT-02 | **本地已实现** |
| `/api/v1/consultant/leads/{id}/status` | PATCH | ENT-03 | **本地已实现** |
| `/api/v1/employee-reports` | POST/GET | ENT-04/05 | **本地已实现** |
| `/api/v1/student-admin/leaves/pending` | GET | ENT-09 | **本地已实现** |
| `/api/v1/student-admin/leaves/{id}/approve` | POST | ENT-09/12 | **本地已实现** |
| `/api/v1/ai/nl2sql/query` | POST | ENT-11 | **本地已实现**（白名单只读） |
| `/api/v1/enterprise/commands` | POST | ENT-12 | **本地已实现** |

> 云端当前仅有 `/health`、`/health/db`；上表 ENT 接口 **尚未在云端**，合并后需 `--build` 方可使用。

## 三、未实现 / 下期（规划）

| 能力 | 任务卡 | 说明 |
| --- | --- | --- |
| 投诉工单列表/更新 | ENT-10 | 待与学生 STU-03 联调 |
| 组织架构查询 | ENT-06 | 表 `sys_organization` |
| 新人指引检索 | ENT-07 | 表 `onboarding_guide` / Dify RAG |
| 成绩录入查询 | ENT-08 | 表 `student_score` |
| 主动待办推送 | ENT-13 | 表 `todo_item` + 定时任务 |
| 统一 auth 鉴权 | — | 暂用 `X-Employee-Id` 头，待 `modules/auth` |
| 学生端提交请假 | STU-01 | 由学生模块负责人实现 |

## 四、跨模块依赖

| 依赖方（你） | 被依赖方 | 约定 |
| --- | --- | --- |
| ENT 审批请假 | `student_admin_service` 表 | 学生助手写入 `pending`，你审批 |
| ENT 指令审批 | `sys_user.real_name` | 按姓名找人，需库里有学生用户 |
| Dify 日报 | `POST /employee-reports` | Dify 做 NLP，你只收结构化 JSON |
| NL2SQL | Dify 输出 `intent`+`params` | **禁止** 传 `sql` / `raw_sql` |
| 附件 | `UPLOAD_DIR` + `modules/files` | 你只存相对路径，上传由他模块做 |

## 五、Dify HTTP 示例（云端）

```
POST http://education-api:8000/api/v1/consultant/leads
POST http://education-api:8000/api/v1/ai/nl2sql/query
Body: {"intent":"lead_follow_ups_by_name","params":{"customer_name":"张三"}}
Header: X-Employee-Id: 1  （可选，数据权限）
```

## 六、本地测试

```powershell
cd aiproject
pytest tests/test_lead_status_rules.py -q
# 有 MySQL 时手动调 Swagger 或用 httpx 测 consultant 接口
```
