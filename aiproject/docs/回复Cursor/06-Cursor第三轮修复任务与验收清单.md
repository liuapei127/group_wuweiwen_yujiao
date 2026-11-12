# 06 · Cursor 第三轮修复任务与验收清单

日期：2026-11-11  
依据：`05-GPT致Cursor-第三轮评审回复.md`

## 1. 执行顺序

1. 读 05，区分 **材料签收** 与 **可发布签收**。  
2. **P1** 默认 `EMPLOYEE_IDENTITY_MODE=blocked` → consultant **503**；健康检查不变。  
3. **P1** 拆分：`run_customer_http_secure_matrix.py`（回归）与 `run_customer_http_insecure_repro.py`（漏洞复现）。  
4. **P1** 修正原 `run_customer_http_matrix.py` 退出语义（或标记 legacy，以 16/17 为准）。  
5. **P2** 补无副作用快照、列表隔离、PATCH 档案、跟进字段级校验（写入 16/17 迭代或 07 记录）。  
6. **P2** 产出 `18-CRM差异判定.md`（非仅采集）。  
7. 更新 `04` 三栏契约表；汇总 `07-Cursor第三轮执行结果.md`。

## 2. P1 身份（已落代码要点）

| 项 | 要求 | 实现 |
| --- | --- | --- |
| 不可信员工头 | 不得决定操作者 | `dependencies.py`：非 `insecure_header_repro` → **503** |
| 服务 Bearer | 可保留，不得冒充员工 | blocked 下 Bearer+头仍 503 |
| 缺陷复现 | 隔离、明示 | 子进程仅设 `EMPLOYEE_IDENTITY_MODE=insecure_header_repro` |
| 生产放行开关 | 禁止 | 无 `ALLOW_*` 默认可合并配置 |

## 3. HTTP 脚本退出语义

| 套件 | 通过含义 | exit 0 条件 |
| --- | --- | --- |
| secure_blocked | 默认部署姿态 | 全部 `REQUIRED_CASES` outcome=PASS |
| insecure_repro | 证明漏洞/回归业务 | 无 FAIL；KNOWN_DEFECT 允许 |

结果字段：`expected` / `actual` / `outcome`（PASS\|FAIL\|KNOWN_DEFECT\|BLOCKED\|SKIPPED）；`started_at` / `finished_at`。

## 4. P2 待补 HTTP（下一轮）

- 每次 403 写请求前后独立 SELECT。  
- A/B 客户列表隔离（owner 过滤、keyword、total）。  
- `PATCH /leads/{id}` 档案。  
- 跟进字段与 `employee_id` body 冲突拒绝。  
- 非法员工头（0、负数、非整数）。  
- DB 故障注入（应用内优先）。

## 5. 结构与安装

- CRM：18 号差异表 + 14 号 JSON 并存；结论句见 05 §2 P2。  
- Python 3.11 双 venv：未执行则标阻塞；可接受 CI/他机 exit 0 附 SHA。  
- Docker：单列未执行。

## 6. 04 号契约表（须三栏）

见更新后的 `04-认证阻塞项与契约待决.md`：**提议方案 / 待定决策 / 实际确认**；集成负责人 **未指定** 则如实写。

## 7. 交付给 GPT（下一轮）

`07` + `16` + `17` + `18` + 更新 `04`；不重发 11。
