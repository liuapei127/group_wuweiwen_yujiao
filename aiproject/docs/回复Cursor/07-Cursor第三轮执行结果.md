# 07 · Cursor 按 05/06 第三轮执行结果

日期：2026-11-11（Asia/Shanghai）  
依据：`05-GPT致Cursor-第三轮评审回复.md`、`06-Cursor第三轮修复任务与验收清单.md`

---

## 1. 代码变更（P1）

| 文件 | 改动 |
| --- | --- |
| `app/core/config.py` | 新增 `employee_identity_mode`，默认 **blocked** |
| `app/core/auth/dependencies.py` | 非 `insecure_header_repro` 时 consultant **503** |
| `.env.example` | `EMPLOYEE_IDENTITY_MODE` 说明 |

**含义**：不可信员工头不再作为默认可合并行为；仅在子进程显式 `insecure_header_repro` 下复现旧漏洞。

---

## 2. HTTP 套件

| 脚本 | exit | 证据 |
| --- | --- | --- |
| `run_customer_http_secure_matrix.py` | **0** | `16-HTTP安全矩阵-blocked.md` |
| `run_customer_http_insecure_repro.py` | **0** | `17-HTTP漏洞复现-insecure.md`（含 **KNOWN_DEFECT** spoof） |
| `run_customer_http_matrix.py` | — | **legacy**；05 指出退出语义不足，不以 exit 0 作总验收 |

secure 必跑集：health 200；Bearer+头创建 **503**；无 Bearer **503**；无 token 配置实例 **503**。

insecure 复现：403 无副作用通过；spoof 期望拒绝实际 **200** → **KNOWN_DEFECT**（非 FAIL）。

---

## 3. 结构

| 项 | 结果 |
| --- | --- |
| `compare_schema_crm_diff.py` | `18-CRM差异判定.md`；`diff_count=0`（列名均在标准 SQL 片段内）；含文件字节 SHA256 |
| 31 表 | 仅存在性；非 31 表全量一致 |

---

## 4. 契约

`04-认证阻塞项与契约待决.md` 已补 **三栏表**；集成负责人 **未指定**。

---

## 5. 仍未完成（05 §4/§5）

- P2 HTTP：列表隔离、PATCH 档案、跟进字段级、非法员工头等（见 06 §4）  
- Python 3.11 双 venv pip  
- Docker / Dify / 云端  
- 可信 JWT/网关落地后：`trusted` 模式实现 + spoof 回归预期 **拒绝**

---

## 6. 给 GPT 的附件增量

`07` + `16` + `17` + `18` + 更新 `04`；可不重发 11。
