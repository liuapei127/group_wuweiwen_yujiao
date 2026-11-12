# 30 · 按 29 号签收与回归加固

日期：2026-11-11  
依据：`29-GPT致Cursor-第九轮评审与P2阶段签收.md`

## 1. 29 号结论（记录）

- **阶段签收**：`aacdf93e5ee8` 样本 — 隔离 HTTP 应用授权层 P2 三组（限定范围，非生产可信身份 / 非发布）。
- **维持未验收**：可信员工身份、`app.main` 真实身份回归、Python 3.11、Docker、云 / Dify。
- **对外表述**：见 29 §5 引语，可直接引用。

## 2. §3 自动回归加固（已落地）

| 项 | 改动 |
| --- | --- |
| 错误响应 | `parse_envelope`：非 200 / 非 `code=0` / 无 `data` 对象 → 失败，零结果用例不再 `or 0` 假 PASS |
| B 侧列表 | 公共关键词 **精确 ID 集合** + `total` 与独立 COUNT |
| 分页 | A/B 均 `page_size=1` 逐页校验长度、owner、total；B 三页 |
| 默认列表 | 本轮标记子集 = `set(leads_a)` 且条数 = 库 COUNT（不声称全库） |
| 跟进 | 创建响应 / 详情 / 库 **六字段**相等（含 `next_plan`） |
| PATCH | 断言 `data.id == patch_target` 且 envelope 合法 |
| 源码绑定 | 输出 `source_fingerprint.sha256`（7 个参与测试的源文件，不含 `.env`） |

## 3. 加固后复跑

| 项 | 值 |
| --- | --- |
| 命令 | `python scripts/run_customer_p2_http.py` |
| run_id | `6f81d1535b0e` |
| 退出码 | 0 |
| 归档 | `runs/p2-6f81d1535b0e.md`、`25-P2-HTTP验收记录.md` |
| fingerprint | `6129cda118d48ffc5e3bee5044cae33419c45677d6910b469034bd32e97b624f` |

## 4. 下一步（29 §5）

1. 公共 auth 契约 + 3.11 可构建环境  
2. 可信 auth 接入后于 `app.main` 复跑 P2，并补身份伪造 / 停用员工等项  
3. 团队将 `aiproject` 纳入版本控制后，以 commit + fingerprint 替代「仅 HEAD」表述

## 5. 后续（31 / 32）

**31 号**确认加固与指纹 `6129cda1…` 一致，维持 29 限定签收，**无需再围绕 P2 补长篇**。本地收口与下一阶段清单见 **32**。
