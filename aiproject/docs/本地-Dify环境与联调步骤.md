# 本地 Dify 环境说明与联调步骤

**结论：Dify 已在你本机装好并在跑，不需要再装一遍。**

| 项 | 你的机器现状 |
| --- | --- |
| Dify 目录 | `D:\tools\dify-1.16.0\docker` |
| 访问 | **`http://127.0.0.1:8088`**（若 80 被 WSL 占用则用 8088；见 `EXPOSE_NGINX_PORT`） |
| Docker | `dify-nginx-1`、`dify-api-1` 等容器 **Up** |
| ENT 后端 | 需另开终端运行 `scripts\start_api_for_dify.ps1` |

---

## 1. 我每天怎么用（两条命令）

**终端 A — API（给 Dify 调）**

```powershell
cd "d:\Project course\group_wuweiwen_yujiao\aiproject"
.\scripts\start_api_for_dify.ps1
```

**终端 B — 自测**

```powershell
curl.exe http://127.0.0.1:8000/health
curl.exe http://127.0.0.1:8000/docs
```

**浏览器 — Dify 控制台**

- http://localhost（若跳 HTTPS 就用 https://localhost）
- 用你 **首次安装 Dify 时注册的账号** 登录（账号在 Dify 自己的库里，不是 MySQL `education_service`）

---

## 2. Dify 里怎么连本机 API

Dify 跑在 **Docker 里**，容器里的 `127.0.0.1` 不是宿主机。

| 场景 | HTTP 节点 Base URL |
| --- | --- |
| Dify Docker → 本机 FastAPI | **`http://host.docker.internal:8000`** |
| 你在浏览器测 Swagger | `http://127.0.0.1:8000` |

**环境变量（建议在 Chatflow 里建）**

- `base_url` = `http://host.docker.internal:8000`

**先做一个探活节点（必过）**

- Method: `GET`
- URL: `{{base_url}}/health`
- 期望 body 含 `"status":"ok"`

**业务节点（当前预期）**

- 例如 `POST {{base_url}}/api/v1/consultant/leads`
- **会返回 503** — 这是身份 blocked，不是 Dify 配错
- Chatflow 里加分支：status=503 → 回复「员工身份未就绪，等待公共登录接入」

详细话术与意图分支见 `客户管理-Dify闭环说明.md`。

---

## 3. 推荐：从 OpenAPI 导入工具（少手填 URL）

1. 先跑起 `start_api_for_dify.ps1`
2. Dify → **工具** → **自定义** → 从 URL 导入 OpenAPI  
   - URL：`http://host.docker.internal:8000/openapi.json`  
   - 若容器访问失败：在 Dify 宿主机网络设置里确认 Windows Docker Desktop 支持 `host.docker.internal`（默认有）
3. 创建 **Chatflow（高级对话）** → 添加 **HTTP 请求** 或绑定刚导入的工具
4. 路径以 Swagger 为准，例如：
   - `POST /api/v1/consultant/leads`
   - `GET /api/v1/consultant/leads`
   - `POST /api/v1/ai/nl2sql/query`

旧文档里 `/crm/leads`、`/ent/...` 等路径 **已过时**，以 `/api/v1/consultant/...` 为准。

---

## 4. 想本地真入库（503 之外）怎么办

| 方式 | 说明 |
| --- | --- |
| **正式** | 等公共 JWT → `app.main` 开放业务 |
| **仅本机彩排** | 另起 `tests.repro`（非默认 8000），Dify 指到该端口；**勿当生产**，勿写进云上 Dify |

答辩、组会对外口径仍以 **blocked + 503** 为准。

---

## 5. Dify 起停（需要时）

```powershell
cd D:\tools\dify-1.16.0\docker
docker compose ps
docker compose up -d    # 启动
docker compose down     # 停止（慎用）
```

不要用 `down -v`，会清 Dify 自己的 Postgres 数据。

---

## 6. 我（Cursor）还缺什么才能替你「全自动配工作流」

本机 Dify **控制台登录态**未接到 Cursor（MCP `auth.status` 无 cookie）。  
请你任选一种：

1. 浏览器登录 Dify 后，用 Cookie 导出插件把 cookie 给集成（见 Dify MCP `auth.import_cookies`）— **别把密码发聊天里**  
2. 或你本人在 UI 按 §2、§3 配；我提供的闭环说明已够用  

登录接上后，我可以用 MCP 帮你 **同步 Chatflow 草稿、发布、跑测试**。

---

## 7. 相关文档

- `客户管理-Dify闭环说明.md` — 意图、节点序列、错误分支  
- `backend/docs/Dify-企业助手HTTP工具配置.md` — 路径注意对照 Swagger  
- `企业智能助手-组会开口稿-2026-11-11.md` — 为何业务 503  
