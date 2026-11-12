# 33 · Python 3.13 目标调整与腾讯云升级准备

日期：2026-11-11

**组内决议：统一使用 Python 3.13.x**（替代原 3.11 目标）。历史 GPT/运行报告中的 3.10/3.11 表述保持不变；自本文件起以后续任务以 3.13 为准。

## 已修改

- pyproject.toml：requires-python = ">=3.13,<3.14"。
- .python-version：3.13。
- Dockerfile：基于 python:3.13-slim，安装项目并以 app.main:app 启动。
- .dockerignore：排除 .env、测试、日志文档与本地虚拟环境。
- aiproject/README.md 与 backend/docs/腾讯云部署与小组协作.md：补充 3.13 创建环境、云端重新构建和版本检查命令。

## 本轮执行

| 验证 | 结果 |
| --- | --- |
| 本地 Docker API 镜像构建，含 pip install . | PASS，退出码 0 |
| 普通安装从 /tmp 导入 app.main | PASS，退出码 0，来自 site-packages |
| 独立容器新建 venv 后 pip install -e . 并从 /tmp 导入 | PASS，退出码 0 |
| 实际解释器 | Python 3.13.18，Linux x86_64 |

完整安装输出、退出码、基础镜像摘要与源码 SHA256 见 34 号 JSON。验证未连接数据库，未执行 DDL，也不表示业务、安全或云端已验收。

## 腾讯云实际状态

已完成仓库中的云端构建配置；尚未连接服务器、上传配置或替换运行中的 API 容器。本机 .ssh 仅有 known_hosts，无可用登录配置/密钥；浏览器入口初始化失败。需提供可用服务器登录入口后继续执行已授权的 API Python 3.13 环境升级。宿主机系统 Python、MySQL 与 Dify 自身镜像不属于本次 API 运行时修改。

可信 auth、app.main 真实身份回归、云端与 Dify 验收仍单列待完成。Windows 原生 Python 仍为 3.10，本轮提供的是可运行的 Docker Python 3.13 环境。
