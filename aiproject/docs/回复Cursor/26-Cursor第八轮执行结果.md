# 26 · 按 23 号第八轮执行结果

日期：2026-11-11  
依据：`23-GPT致Cursor-第七轮评审回复.md`、`24-Cursor第八轮修复任务.md`

---

## 1. 23 号认定（我方复述）

**已关闭 / 可签收**：默认 blocked、app 隔离、19 导出与人工结论分离、CRM 快照核对表述。  
**仍不签收**：P2、可信 auth、3.11、Docker、云/Dify、整体阶段。  
**正常 app.main** 继续 503；**不可**将 repro 下业务通过当作可信身份验收。

---

## 2. P2 三组（23 §4）

**命令**：`python scripts/run_customer_p2_http.py`  
**入口**：`tests.repro.asgi_app`（`layer=application_auth_under_repro_not_trusted_identity`）  
**run_id**：`bee3b44754e5` · **exit 0**  
**git_sha**：`177df8fa856d537c38e84a7bc77a378eb263d328`  
**证据**：`25-P2-HTTP验收记录.md`、`runs/p2-bee3b44754e5.md`

| 用例 | 结果 |
| --- | --- |
| 列表 A/B 关键词隔离 | PASS |
| 员工 B 指定 owner=1 列表 | 403 PASS |
| 本人 PATCH 档案 | PASS |
| 他人 PATCH 无副作用 | PASS |
| 跟进详情与 SELECT 一致 | PASS |
| body employee_id 冲突 | 403 PASS |

**security_acceptance**：**FAIL**（仅应用内授权逻辑，非真实员工身份）

---

## 3. 单元检查（对齐 23 命名）

`run_unit_auth_tests.py` → 三项 PASS（含 stderr RuntimeError 校验）

---

## 4. 仍未完成

- 可信 JWT / 网关（`app.main` 业务仍 503）  
- Python 3.11 pip、Docker、Dify、云端  
- P2 在 **正常入口 + 可信身份** 下的复跑（待 auth 契约）  

---

## 5. 汇报句

> P1 配置/隔离/CRM 表述 **23 号已签收**；P2 三组在 **repro 应用内** 已有 HTTP+查库证据；**整模块仍不能发布**，因可信身份与部署链路未验收。
