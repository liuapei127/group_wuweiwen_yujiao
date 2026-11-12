# 6 · 客户管理 API 接口文档（R2 · 含认证）

**Base**：`http://127.0.0.1:8000` 或云端 `http://education-api:8000`（build 后）

## 认证（所有 `/api/v1/consultant/*` 业务接口）

| 请求头 | 必填 | 说明 |
| --- | --- | --- |
| `Authorization` | 是 | `Bearer <AUTH_BEARER_TOKEN>`，与 `.env` 一致 |
| `X-Employee-Id` | 是 | 整数，当前登录员工 ID（Bearer 通过后才可信） |
| `Content-Type` | POST/PATCH | `application/json` |

| HTTP | 含义 |
| --- | --- |
| 401 | 未认证 / 凭据无效 / 缺少员工 ID |
| 503 | `AUTH_BEARER_TOKEN` 未配置 |
| 403 | 非本人 owner 的客户 |
| 404 | 客户不存在 |
| 409 | 非法状态转换 |
| 422 | 参数/业务校验（如流失无原因） |

成功时仍用 body：`{"code":0,"message":"...","data":...}`（HTTP 200）。

---

## 接口列表

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/health` | 存活（无认证） |
| GET | `/health/db` | 库连通（无认证） |
| POST | `/api/v1/consultant/leads` | 录入；`owner_employee_id` 须等于 `X-Employee-Id` |
| GET | `/api/v1/consultant/leads` | 列表；默认过滤当前员工 |
| GET | `/api/v1/consultant/leads/{id}` | 详情+跟进 |
| PATCH | `/api/v1/consultant/leads/{id}` | 改档案 |
| PATCH | `/api/v1/consultant/leads/{id}/status` | 改状态 |
| POST | `/api/v1/consultant/leads/{id}/follow-ups` | 写跟进 |

---

## 录入示例（脱敏）

```http
POST /api/v1/consultant/leads
Authorization: Bearer <从.env读取，勿写入文档>
X-Employee-Id: 1

{
  "customer_name": "测评客户[E2E标记]",
  "contact_info": "139****1234",
  "owner_employee_id": 1,
  "intended_country": "德国",
  "remark": "E2E标记"
}
```

完整字段见 OpenAPI：`/docs`（服务启动后）。

---

## 部署状态

| 接口组 | 云端 |
| --- | --- |
| `/health`, `/health/db` | ✅ |
| `/api/v1/consultant/*` | ❌ 待合并 build |
