# 2026-11-18 项目展示版：代码、Dify 与本地数据

> 学生助手的后续独立修复见 [学生助手代码与画布更新](../2026-11-18-student-assistant-update/README.md)。使用该更新的代码时，请导入新目录的学生画布；本目录原有 DSL 和校验值保留为基线快照。

对应分支：`codex/v11-integration`。本目录包含当前已发布 Dify 工作流和可独立导入的业务数据。组员在各自电脑上测试，无需连接原开发电脑的数据库。

## 本次内容

- 客服会话记忆、通用用户画像、双端共享资料、上传归属核对和资料文件查看。
- 顾问研判区分内部跟进建议与面向客户的沟通话术。
- 学生助手采用最新 22 节点 workspace 工作流。
- 修复安全审计详情空白；移除员工报告详情中的 AI 总结卡片。
- 新展示资料包含 110 个官网账号（含 42 位学生、40 位已认领客户和 28 位待认领访客）、124 位客户、6 个班级、4 位班主任、7 位在职顾问，以及资料文件、成绩、申请进度、考务、请假、反馈、活动、日报周报和待办。

资料为合成展示数据；正常姓名和业务关系均已整理。当前开发电脑的原始备份、真实密码哈希、访问会话、数据库密码、JWT 私钥、Dify/模型服务密钥不在交付包中。导出副本中的业务账号统一使用下述本地展示密码，原开发电脑的员工密码不变。

## 1. 准备本机环境

需要 Python 3.13、MySQL 8.0+、Node.js 与可用的 Dify。以下命令在仓库的 `aiproject` 目录运行，示例使用 Windows PowerShell。

```powershell
py -3.13 -m venv .venv313
.venv313/Scripts/python.exe -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

编辑本机 `.env`，填写自己的 MySQL 连接信息：

```dotenv
DB_HOST=127.0.0.1
DB_PORT=3306
DB_NAME=education_service_showcase
DB_USER=root
DB_PASSWORD=填写本机MySQL密码
UPLOAD_DIR=./data/uploads
```

已有 `.env` 的组员保留自己的配置并调整目标库名；不要覆盖已有密钥。

## 2. 导入展示库

```powershell
.venv313/Scripts/python.exe -m scripts.import_showcase_data --database education_service_showcase
```

脚本校验压缩文件 SHA256，创建明确指定的本地库，导入并核对 87 张表的数据量、4 个触发器、关联关系及学生/客户身份一致性。目标库已有表时直接拒绝，避免覆盖组员原有资料。改用其他新库名时，必须同步调整 `.env` 的 `DB_NAME`。

这是完整当前表结构快照，已包含本轮迁移；导入后不要再次执行旧建库脚本或逐个重放已有迁移，也不要运行旧的联调账号初始化脚本覆盖展示姓名。

原始 SQL 压缩包：`database/showcase.mysql.sql.gz`；校验值、各表行数和全部展示账号见 `database/manifest.json`。

## 3. 为本机生成认证配置

```powershell
.venv313/Scripts/python.exe -m scripts.generate_local_demo_keys
Get-Content logs/showcase-local-settings.env | Add-Content .env -Encoding utf8
```

脚本生成各自独立的 RS256 密钥和学生外部知识检索 token，保存在 Git 忽略的 `logs` 目录。已有有效 BASE 认证配置时可复用自己的密钥；生成器发现同名文件会拒绝覆盖。前端地址必须和 `BASE_PORTAL_ORIGIN=http://127.0.0.1:5193` 一致。

## 4. 导入 Dify

从本目录 `dify` 中导入，使用原生 DSL，来源是当前工作区的**已发布版本**：

| 文件 | 用途 | 节点数 | 后端配置 |
|---|---|---:|---|
| `cs.yml` | 官网客服 | 36 | `CS_PUBLIC_DIFY_API_KEY` |
| `stu-workspace.yml` | 学生助手、草稿与确认 | 22 | `STU_DIFY_API_KEY`、`STU_ASSISTANT_MODE=workspace` |
| `pf.yml` | 客户研判与顾问建议 | 9 | `PF_DIFY_API_KEY` |
| `ent.yml` | 企业助手 Chatflow | 32 | `DIFY_ENT_CHATFLOW_API_KEY` |
| `rpt.yml` | 员工正式报告工作流 | 4 | `DIFY_EMPLOYEE_FORMAL_API_KEY` |
| `ent-fallback.yml` | 企业助手备用参数理解 | 3 | `DIFY_WORKFLOW_API_KEY`（可选） |

在自己的 Dify 配置导出文件所需的模型供应商和插件（当前主要使用通义 `qwen-plus`），导入后核对模型节点，再发布并生成自己的应用 API Key。应用 Key 仅填到本机 `.env`。`DIFY_API_URL` 填本机实例的服务 API 根地址，例如 `http://127.0.0.1:18088/v1`；端口按自己的 Dify 实例调整。

跨工作区知识库 ID 不通用，必须重新绑定：

1. `dify/knowledge` 中有公司简介、常见问题、留学项目、政策入口四个知识库的 9 份当前文档。按目录创建知识库、导入对应文件并完成索引，然后在 CS 检索节点重新选择各自的知识库。检索向量模型也要改成自己的可用模型。
2. 学生使用两份外部知识库，命名可为“学生生活指南 · 德国”“学生生活指南 · 新加坡”。外部接口填写 `http://host.docker.internal:8003/api/v1/student/knowledge`；knowledge_id 分别为 `Germany`、`Singapore`；鉴权 token 取本机 `STU_KNOWLEDGE_TOKEN`。重新绑定学生工作流中的两国检索节点。
3. 两国生活指南正文已在数据库快照的 `overseas_life_knowledge` 中，源文件仍在 `docs/student-workspace/overseas-life-catalog.json`。
4. 研判规则与项目资料附在 `dify/knowledge/研判规则与项目资料`，与本轮通用画像结构配套。无需按国家另建客户属性。
5. CS 环境变量 `cs_api_base` 使用 Dify 容器能访问的后端地址；本机 Docker Desktop 通常为 `http://host.docker.internal:8003`。Linux Docker 需配置宿主机网关或使用可达的后端地址。

各应用节点数、发布版本编号和 DSL 校验值见 `dify/manifest.json`。工作流导出不包含模型供应商账号、API Key 或 Dify 数据库；这些由各组员在自己的工作区配置。

## 5. 启动

后端终端：

```powershell
.venv313/Scripts/python.exe -m uvicorn app.main:app --env-file .env --host 0.0.0.0 --port 8003
```

`--env-file .env` 必须保留，BASE JWT 读取进程环境中的密钥文件配置。Dify 需要访问学生公开知识接口时，后端绑定地址需要能被本机容器访问。

前端另开终端：

```powershell
cd frontend
npm ci
$env:ENT_DEV_API_URL="http://127.0.0.1:8003"
npm run dev -- --host 127.0.0.1 --port 5193 --strictPort
```

员工入口：`http://127.0.0.1:5193/`；官网：`http://127.0.0.1:5193/website`。检查 `/api/v1/auth/status` 应返回 `mode=base_rs256`、`ready=true`。

## 6. 本地展示账号

**导入副本中所有业务账号的统一密码：`YuejiaoDemo_2026!`**。只用于各自本地展示库。

| 身份 | 姓名 | 登录手机号 |
|---|---|---|
| 管理员 | 何嘉敏 | `19900001101` |
| 顾问 | 周景明 | `19900001102` |
| 主管 | 林若溪 | `19900001103` |
| 班主任 | 陈思齐 | `19900001104` |

官网学生和客户账号、姓名及手机号见 `database/manifest.json` 的 `accounts`。建议先用顾问查看资源池和客户资料，再以同一位学生的官网账号查看学籍、申请和考务，最后由班主任查看班级、成绩及审批。

## 验证记录

- 原库重建通过外键、同人账号继承、画像一致、班主任与国家、成绩课程、活动人数和时间顺序检查。
- 本交付 SQL 已导入独立本地库 `education_service_team_verify_20261118` 并核对全部表和触发器，未切换当前项目使用的数据库。
- 当前展示库通过四角色真实登录、官网访客/客户/学生登录、双端画像和资料文件读取，以及 7 个实际页面检查。
- 当前 Dify 的两条展示案例实际调用成功，跟进建议与客户话术分别返回。
- 本次后端隔离测试 808 项通过（使用 `STU_ASSISTANT_MODE=legacy` 跑既有完整回归），前端构建通过，客服画像与审计浏览器回归 10 项通过。workspace 学生助手另按当前实际运行版本验证；新导入副本也已用独立 RS256 密钥完成四角色登录和学生账号/画像读取检查。
