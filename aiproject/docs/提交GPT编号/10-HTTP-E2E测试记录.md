# 10 · 客户管理 HTTP E2E 测试记录（实证）

**执行时间**：2026-11-11T17:18:18（本机）  
**命令**：`python scripts/run_customer_http_e2e.py`  
**条件**：`127.0.0.1:8765` 起 Uvicorn；MySQL `education_service`；`.env` 已配置 `AUTH_BEARER_TOKEN`（值不入库、不写本文）  
**标记**：`E2E_HTTP_20261111_171814`  
**脚本退出码**：0  

## 结果摘要

| 步骤 | HTTP 状态 | 结论 |
| --- | --- | --- |
| 带 Bearer 创建客户 | 200 | 成功，`lead_id=1` |
| 列表 / 详情 | 200 | 命中标记 |
| 状态 `new` → `contacting` | 200 | 成功 |
| 再查详情 | 200 | `status=contacting` |
| **无 Bearer 创建** | **401** | `{"detail":"未认证"}` |
| MySQL 核对 | — | `crm_lead.remark` 与状态一致 |

## 未在本脚本覆盖（评审关注点）

- **未测**：503（无 `AUTH_BEARER_TOKEN` 启动）
- **未测**：403（他人 `owner` / 伪造 `X-Employee-Id` 改状态）
- **身份可信**：见 `12-评审三项回应与实证.md` §1 — Bearer 通过即可任意填 `X-Employee-Id`，**不能**算作员工身份已验证

## 完整 JSON 日志

见同目录上级：`../客户管理-HTTP-E2E测试记录.md`（与本文同内容）。终端拷贝：`12-附录-HTTP-E2E终端输出.txt`。
