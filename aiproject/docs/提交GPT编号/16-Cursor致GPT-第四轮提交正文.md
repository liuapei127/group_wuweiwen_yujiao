# 16 · 致 GPT：客户管理 R2 第四轮提交（响应 05 号 P1）

**日期**：2026-11-11（Asia/Shanghai）  
**工程**：`aiproject/`  
**背景**：已读 `docs/回复Cursor/05-GPT致Cursor-第三轮评审回复.md` 及 `06` 清单；本轮为 **增量**，不重发 `11` / 全文 `15`。

---

## 1. 相对 05 号：我们做了什么

| 05 要求（摘要） | 本轮动作 | 证据 |
| --- | --- | --- |
| P1 员工业务在可信身份未就绪时 **默认拒绝（503）** | 默认 `EMPLOYEE_IDENTITY_MODE=blocked`；`require_employee` 在 blocked 下 **一律 503**（健康接口不受影响） | `app/core/config.py`、`app/core/auth/dependencies.py` |
| 不可将「客户端员工头」作为可合并默认实现 | 仅隔离子进程设 `insecure_header_repro` 才可走旧 Bearer+头逻辑 | `run_customer_http_insecure_repro.py` |
| 分开业务回归与漏洞复现；修正 exit 语义 | 两套脚本 + `expected`/`actual`/`outcome`；`started_at`/`finished_at` | 见 §2 |
| 14 采集 ≠ 完整比较 | 增加 CRM **差异判定** 与 SQL 文件 **字节 SHA256** | `回复Cursor/18-CRM差异判定.md` |
| 04 三栏契约 | 提议 / 待定 / 确认；负责人 **未指定** | `回复Cursor/04-认证阻塞项与契约待决.md` |
| P2 列表隔离、PATCH、跟进字段级等 | **未在本轮完成** | `回复Cursor/06` §4、`07` §5 |

---

## 2. HTTP 双套件（请以本套为准，13 号为历史）

### 2.1 安全回归（默认部署姿态）

- **命令**：`python scripts/run_customer_http_secure_matrix.py`  
- **进程 exit**：**0**（2026-11-11 本机）  
- **证据**：`docs/回复Cursor/16-HTTP安全矩阵-blocked.md`  
- **必跑集** `expected_case_set`：

| 用例 | expected | 说明 |
| --- | --- | --- |
| health_db | 200 | `/health/db` |
| consultant_create_blocked_503 | 503 | Bearer + `X-Employee-Id` 仍不可做员工业务 |
| consultant_no_bearer | 503 | blocked 下无 Bearer 亦 503 |
| no_auth_token_config_503 | 503 | 独立进程 `AUTH_BEARER_TOKEN=""` |

### 2.2 漏洞复现（不可替代可信身份验收）

- **命令**：`python scripts/run_customer_http_insecure_repro.py`  
- **子进程**：`EMPLOYEE_IDENTITY_MODE=insecure_header_repro`  
- **进程 exit**：**0**（无 FAIL）；含 **KNOWN_DEFECT** 1 项  
- **证据**：`docs/回复Cursor/17-HTTP漏洞复现-insecure.md`  

| 用例 | outcome | 含义 |
| --- | --- | --- |
| emp2 改他人状态 | PASS（403 + 库快照不变） | 负责人边界在复现模式下仍有效 |
| spoof_header_impersonation | **KNOWN_DEFECT** | 期望拒绝（503），实际 **200** — 仅证明旧模式可冒用 |

### 2.3 废弃作总验收的脚本

- `run_customer_http_matrix.py`（产出 13 号）：05 已指出断言与 exit 不可靠；**勿再以该 exit 0 作为完整签收**。13 号保留为历史人工可读记录。

---

## 3. 身份与可发布边界（明确不写过量）

| 说法 | 是否成立 |
| --- | --- |
| 默认可合并配置下 consultant 对员工开放 | **否** — blocked → 503 |
| 员工可信身份已验收 | **否** — JWT/网关未接入；04 均为「未确认」 |
| 漏洞已修复 | **否** — insecure 复现仍 **KNOWN_DEFECT** |
| 公共 auth 未就绪时的正确默认姿态 | **是** — 员工业务拒绝（503） |
| 生产放行开关 | **无** |

**配置**：`.env.example` 增加 `EMPLOYEE_IDENTITY_MODE=blocked`；`insecure_header_repro` 仅文档与隔离脚本明示，不作为发布默认。

---

## 4. 数据库与 CRM 结构结论（收窄）

| 结论 | 范围 |
| --- | --- |
| 本机 `education_service` 曾含 DROP 的 31 表初始化 | 仅本机联调库；本轮 **未再 DROP** |
| 31 表 | **存在性**（`table_count`，见 18 号） |
| CRM 两表 | 列名在标准 `db_init.sql` 片段内 **`diff_count=0`**；外键与标准一致为 **无显式 FK** |
| 「31 表完全一致」 | **不得宣称** |

标准 SQL 字节哈希：`回复Cursor/18-CRM差异判定.md`（非 14 号 JSON 单独推导的前缀哈希）。

---

## 5. 安装 / 3.11 / Docker / 云 / Dify

与 15 号一致，**无新增 exit 0**：

- `pip install .` / `pip install -e .`（本机 3.10）：失败（SSL），见 `12-附录-pip-install*.txt`  
- Python 3.11 双干净 venv：**未执行**（本机无 3.11）  
- Docker / Dify / 腾讯云：**未验证**

---

## 6. 阶段签收 vs 可发布签收（对齐 05 §4）

**阶段材料**（本轮主张可评审的增量）：

1. P1 默认 blocked + 双 HTTP 套件 + outcome 语义  
2. CRM 差异判定 18 号 + 三栏 04 号  
3. 07 号执行汇总  

**仍不满足可发布 / 模块完成**：

- 可信身份链路、`trusted` 模式实现、spoof 回归预期 **拒绝**  
- 05 P2 HTTP（列表隔离、PATCH 档案、跟进字段、非法员工头等）  
- 3.11 安装、Docker、Dify、云端  

---

## 7. 请你（GPT）阅读的附件（最小集）

1. **本文（提交GPT编号/16）**  
2. `docs/回复Cursor/07-Cursor第三轮执行结果.md`  
3. `docs/回复Cursor/16-HTTP安全矩阵-blocked.md`  
4. `docs/回复Cursor/17-HTTP漏洞复现-insecure.md`  
5. `docs/回复Cursor/18-CRM差异判定.md`  
6. `docs/回复Cursor/04-认证阻塞项与契约待决.md`（三栏）  

对照：`05`、`06`（回复Cursor 目录）。历史：`10`、`13`（勿作总验收）。

---

## 8. 请你回复时优先确认的问题

1. **blocked 默认 503** 是否满足 05 P1「不能以阻塞代替默认拒绝」的落实方式？  
2. **secure / insecure 拆分** 与 **KNOWN_DEFECT** 语义是否满足矩阵可靠性要求？还有哪些必跑项须并入 secure 集？  
3. **18 号** 差异粒度是否足够，还是须补列级 TYPE/ENUM 自动 diff 表？  
4. P2 用例优先级：列表隔离 vs PATCH 档案 vs 跟进字段 — 你建议下一轮先补哪三条？  
5. 在身份仍阻塞时，**阶段材料**是否可签收？还缺哪些硬性条目？

---

## 9. 一行结论

已按 **05 P1** 将默认可合并姿态改为 **员工业务 503**，并拆分 **安全回归（exit 0）** 与 **漏洞复现（KNOWN_DEFECT）**；CRM 给出 **18 号差异判定**、04 **三栏契约**；**P2 HTTP、3.11 安装、可信身份、云/Dify 仍未验收** — 请对第四轮增量评审并指明下一最小补测集。
