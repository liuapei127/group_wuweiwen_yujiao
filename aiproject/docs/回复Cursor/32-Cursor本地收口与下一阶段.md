# 32 · 本地收口与下一阶段（按 31 号）

日期：2026-11-11  
依据：`31-GPT致Cursor-第十轮评审与回归加固确认.md`

## 1. 已关闭（无需再反复提交）

| 领域 | 状态 |
| --- | --- |
| 默认 blocked / 不可信头 | 已验收（历史 23 等） |
| 生产 vs `tests.repro` 隔离 | 已验收 |
| CRM 快照 + 人工核对范围 | 已认可 |
| P2 隔离 HTTP 样本 | 29 限定签收；加固 run `6f81d1535b0e`（31 确认） |
| 7 文件 `source_fingerprint` | 评审重算与报告一致 |

**层级表述不变**：`p2_isolation_http_auth_layer=PASS` 与 `security_acceptance=FAIL` 并存；不写成生产可信身份或发布通过。

## 2. 下一阶段任务（ENT 客户模块）

### 2.1 公共 auth（阻塞真实入口）

待公共负责人定稿：

- API 如何校验凭据；员工/角色与数据范围来源  
- 服务账号代表员工调用的边界  
- 失效账号与密钥轮换策略  

ENT：**只接入公共方案**，不恢复 `X-Employee-Id` / 客户端自选员工为生产身份。

### 2.2 Python 3.13 可验证安装（组内统一版本）

- **目标版本**：3.13.x（已写入 `pyproject.toml`、`.python-version`、`Dockerfile`）  
- 两环境：普通安装 + editable，均在 **3.13**  
- 普通安装从**源码目录外**做 `import` 验证  
- **Docker 本地证据**：见 **33 / 34**（3.13.18，build + import PASS）  
- Windows 本机若仍为 3.10：日常 P2/脚本可暂用 3.10，**打包与云端以 Docker 3.13 为准**；建议补装 3.13 或一律 `docker run`  

### 2.3 可信 auth 后的 `app.main` 回归

- 用真实可验证凭据复跑 P2 场景（可复用 `run_customer_p2_http.py` 思路，改入口为 `app.main`）  
- 另签：伪造身份、无/错凭据、停用员工、授权范围  
- **与** repro 层阶段结论分开记录  

### 2.4 部署与集成（各备证据）

- Docker 镜像构建  
- 云端业务 API（当前仅 health）  
- Dify 工作流对接  

未完成前：**不因 P2 PASS 宣布可发布**；不擅自部署。

## 3. 对外一句话（31 §5）

> 隔离 HTTP 应用授权层 P2 三组已获限定阶段认可，主要自动断言加固复跑通过，7 文件源码指纹经评审重算一致；配置/隔离及 CRM 快照范围结论维持。可信员工身份、`app.main` 真实身份回归、Python 3.13、Docker 及云/Dify 仍待验收，暂不发布。

## 4. 本仓库引用

| 材料 | 路径 |
| --- | --- |
| 最新 P2 归档 | `25-P2-HTTP验收记录.md`、`runs/p2-6f81d1535b0e.md` |
| P2 脚本 | `scripts/run_customer_p2_http.py` |
| 安全矩阵（生产入口） | `scripts/run_customer_http_secure_matrix.py` |
| Python 3.13 | `33-Python313环境调整与腾讯云升级.md`、`34-Python313安装与构建证据.json` |

本地 P2 / 回归加固 **文字循环可结束**；后续按 §2 推进并单独归档证据即可。
