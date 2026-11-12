# 10 · Cursor 按 08/09 第五轮执行结果

日期：2026-11-11（Asia/Shanghai）  
依据：`08-GPT致Cursor-第四轮评审回复.md`、`09-Cursor第五轮修复任务与验收清单.md`

---

## 1. 针对 08 号 P1-1（发布代码隔离）

| 项 | 状态 |
| --- | --- |
| 生产 `require_employee` 仅 503，不读 Bearer/员工头 | ✅ |
| `insecure_header_repro` 从生产依赖移除 | ✅ |
| 漏洞逻辑迁至 `tests/repro/insecure_auth.py` + `tests.repro.asgi_app` | ✅ |
| `app.main`  import 时拒绝 insecure 模式 | ✅ `main_rejects_insecure_mode` PASS（exit_code 1） |
| 无「切换复现模式」类对外文案 | ✅ |

---

## 2. 针对 08 号 P1-2（repro 精确判定）

| 项 | 状态 |
| --- | --- |
| 必跑集合 REQUIRED（5 项） | ✅ |
| spoof：200 + code 0 + new→contacting 库证据 | ✅ **KNOWN_DEFECT** |
| `security_acceptance=FAIL` | ✅ 写入 17 号 |
| 非 503 且未写入 → FAIL/NOT_REPRODUCED | ✅ 逻辑已改 |

**命令**：`python scripts/run_customer_http_insecure_repro.py` → **exit 0**（复现成功，非安全通过）

---

## 3. secure 矩阵扩展

| 项 | 状态 |
| --- | --- |
| 多路由 503（创建/列表/详情/PATCH 档案/状态/跟进） | ✅ |
| 动态端口 + `run_id` | ✅ |
| `main_rejects_insecure_mode` | ✅ |

**命令**：`python scripts/run_customer_http_secure_matrix.py` → **exit 0**

证据：`16-HTTP安全矩阵-blocked.md`、`17-HTTP漏洞复现-insecure.md`

---

## 4. CRM（08 §5）

| 项 | 状态 |
| --- | --- |
| 收窄 18 号「diff_count=0」表述 | ✅ 见 `19-CRM逐维差异表.md` |
| 自动 diff 脚本问题 | 未重写解析器；用人表满足最小交付 |

---

## 5. 04 号

已更新 §2：**分模式表**（blocked / trusted / tests.repro）。

---

## 6. 仍未完成（08 §5–7）

- P2：列表隔离、PATCH 档案 HTTP、跟进字段级  
- Python 3.11 双 venv pip  
- Docker / Dify / 云端  
- 可信 JWT `trusted_jwt` 实现  
- **05 阶段材料全部完成**：仍 **不能** 签收（身份未闭环、P2 等）

---

## 7. 提交 GPT 增量建议

`10`（本文）+ `16` + `17` + `19` + 更新 `04`；可选简述相对 16 号第四轮提交的代码差异。
