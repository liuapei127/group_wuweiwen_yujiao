# aiproject（与腾讯云 `/home/ubuntu/education-service/aiproject` 同结构）

本地开发 → 合并 → 云端 **重新 build 镜像**（不能只 restart）。

运行环境统一为 **Python 3.13.x**；云端 API 使用 `python:3.13-slim`。

## 本地启动

```powershell
cd aiproject
copy .env.example .env
# 填写 DB_*，本地 MySQL 库 education_service
py -3.13 -m venv .venv313
.\.venv313\Scripts\Activate.ps1
python -m pip install -e ".[dev]" -i https://mirrors.cloud.tencent.com/pypi/simple
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Swagger：<http://127.0.0.1:8000/docs>

## 云端部署（由组长统一执行）

```bash
cd /home/ubuntu/education-service
sudo docker compose -f compose.yaml -f aiproject/compose.api.yaml -f aiproject/compose.network.yaml up -d --build --no-deps api
sudo docker compose -f compose.yaml -f aiproject/compose.api.yaml -f aiproject/compose.network.yaml exec -T api python --version
```

Dify HTTP Base：`http://education-api:8000`

## 文档

- `docs/ENT-迁移与接口清单.md` — 迁移映射、已实现/未实现接口

## 目录说明（ENT）

| 模块 | 路径 | 职责 |
| --- | --- | --- |
| 意向客户 | `modules/consultant` | 录入/查询/跟进/状态 |
| 员工日报 | `modules/employee_report` | 口述日报结构化入库与查阅 |
| 学生行政 | `modules/student_admin` | 请假待办与审批（与学生助手共用表） |
| 指令 | `modules/enterprise_ops` | Dify 解析后的写操作 |
| NL2SQL | `ai/nl2sql` | 白名单只读查询 |

## 目录框架与后续开发

后续代码遵循 [架构约定](docs/architecture.md) 和 [AGENTS.md](AGENTS.md)。新增功能按 router / schemas / models / repository / service 分层；成绩位于 app/modules/score。其余 ENT 扩展分为 organization、onboarding、feedback、todo。旧 enterprise_support 仅作导入兼容。

模型在 app/model_registry.py 注册，路由在 app/router_registry.py 注册。框架预留包不代表业务已完成。

本地回归：`.venv313/Scripts/python.exe -m pytest tests -q`。
