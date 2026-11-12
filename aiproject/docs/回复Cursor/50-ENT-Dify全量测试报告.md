# 50 ENT · Dify 全量测试报告（过夜交付）

| 项 | 内容 |
| --- | --- |
| **报告时间** | 2026-11-12 00:20（本地） |
| **交付人** | Cursor（刘培阳 ENT） |
| **Dify 应用** | **企业智能助手-ENT** |
| **应用 ID** | `ac18cfb8-3f60-406f-99dd-d9cc635dc71f` |
| **控制台** | http://127.0.0.1:8088/app/ac18cfb8-3f60-406f-99dd-d9cc635dc71f/workflow |
| **ENT API** | `http://127.0.0.1:8000`（宿主机）；Dify 容器用 `http://host.docker.internal:8000` |
| **工作流版本** | **已发布 v1**（10 节点）；**v2 图在仓库待同步**（见 §6） |

---

## 1. 执行摘要（明早 30 秒）

| 维度 | 结果 | 说明 |
| --- | --- | --- |
| **工作流已搭建并发布** | ✅ | 探活 → LLM → 代码 → 分支 → HTTP → 回复 |
| **Docker → API 探活** | ✅ | `host.docker.internal:8000/health` → `{"status":"ok"}` |
| **员工业务 API（main）** | ✅ 符合预期 | `POST /consultant/leads` → **503**（blocked） |
| **Dify 对话全量用例** | ⚠️ | 4 条已跑；2 通过、1 部分、1 失败（见 §4）；**v2 修复已写好未推到控制台** |
| **pytest 全量** | ✅ | **44 passed** |
| **可宣称「CRM 已入库」** | ❌ | JWT 未接入前 **禁止** |

---

## 2. 环境与前置（过夜时已做）

1. **Dify**：`127.0.0.1:8088`（80 口被 WSL 占用，已改 `EXPOSE_NGINX_PORT=8088`）  
2. **FastAPI**：已启动 `uvicorn app.main:app --host 0.0.0.0 --port 8000`（你明早若 8000 无响应，再跑 `scripts\start_api_for_dify.ps1`）  
3. **工作流**：经浏览器控制台 API **同步 + 发布**（hash 成功）  
4. **图定义文件**：`aiproject/docs/dify/ent-workflow-graph.json`  
5. **辅助脚本**：`scripts/run_ent_dify_acceptance.py` → JSON `docs/回复Cursor/runs/ent-dify-acceptance-latest.json`

---

## 3. 基础设施测试

| # | 用例 | 期望 | 实测 | 结论 |
| --- | --- | --- | --- | --- |
| I1 | `GET 127.0.0.1:8000/health` | 200 + ok | 200 `{"status":"ok"}` | ✅ |
| I2 | `POST .../consultant/leads`（无 JWT） | 503 | 503 + 中文 detail | ✅ |
| I3 | Dify 容器内 curl health | 200 | `{"status":"ok"}` | ✅ |
| I4 | `pytest tests -q` | 全绿 | **44 passed** | ✅ |

---

## 4. Dify 工作流对话测试（草稿运行 / streaming）

明细 JSON：`docs/回复Cursor/runs/ent-dify-workflow-runs-2026-11-12.json`

| # | 用户输入 | 工作流终态 | 关键观察 | 结论 |
| --- | --- | --- | --- | --- |
| D1 | 后端健康检查 | **succeeded** | 节点「API探活」200，body `status:ok`；回复说明 JWT/503 风险 | ✅ |
| D2 | 录入客户：晨晨验收001… | **succeeded** | LLM 输出 `ENT_ACTION` JSON，**未触发 POST**（v1 code 未解析） | ⚠️ v1 缺陷 |
| D3 | 查询客户 张三 | **failed** | GET leads 真打 API→**503**；HTTP 节点报错中断 | ⚠️ 预期 503，但应用层应继续（v2 修） |
| D4 | 什么是503 | **succeeded** | 解释 503/JWT，未谎称录入成功 | ✅ |

**节点拓扑（10 节点 / 10 边）**

`用户输入 → API探活 → 意图与回复(LLM) → 解析ENT动作(code) → 需要调API?(if) → POST还是GET → POST录入 / GET查询 → 直接回复`（另：不调 API 时走「仅LLM回复」）

---

## 5. 与需求的符合性（ENT-01～03 + Dify）

| 需求 | v1 已发布 | 明早验收建议 |
| --- | --- | --- |
| 健康探活 | ✅ HTTP 节点 | 预览再问「后端是否正常」 |
| 自然语言意图 | ✅ LLM | 录入/查询/解释 503 |
| 调 FastAPI 录入 | ⚠️ v1 未 POST；v2 会 POST 并展示 503 body | 同步 v2 后重试 D2 |
| 调 FastAPI 查询 | ⚠️ v1 503 导致工作流失败 | v2 应 **succeeded** 且回复含 503 说明 |
| 不编造成功 | ✅ LLM 话术 | 看 D2/D3 是否出现「已录入成功」——不应出现 |

---

## 6. v2 修复（仓库已有，待你明早 1 分钟同步）

**文件**：`docs/dify/ent-workflow-graph.json`

| 修复 | 说明 |
| --- | --- |
| code 解析 | 强化 `ENT_ACTION` 正则 + 录入/查询关键字兜底 |
| if 条件 | 由 `skip is false` 改为 `intent is not other` |
| HTTP 503 | POST/GET 节点增加 `error_strategy: default-value`，**503 不再整图失败** |
| 回复模板 | 展示 status_code + body，并提示 503≠成功 |

**明早同步步骤（任选其一）**

**A. 自动（推荐）**

```powershell
cd aiproject\docs\dify
.\.venv313\Scripts\python.exe cors_http_server.py
```

浏览器打开编排页并保持登录 → 在控制台执行 `browser_sync_workflow.js` 逻辑（或让 Cursor 再跑一轮 sync）。

**B. 手工**

编排页 → 对照 `ENT-企业助手-Chatflow搭建清单.md` 改 code / HTTP 异常策略 → 发布。

---

## 7. 明早验收清单（复制打勾）

- [ ] `curl http://127.0.0.1:8000/health` → ok  
- [ ] Dify 打开：http://127.0.0.1:8088/app/ac18cfb8-3f60-406f-99dd-d9cc635dc71f/workflow  
- [ ] **同步并发布 v2** 图（§6）  
- [ ] 预览：**录入客户测试** → 回复含 **503** 或 API body，**无「已录入成功」**  
- [ ] 预览：**查询客户 张三** → 工作流 **succeeded**，body 含 consultant 不可用  
- [ ] `python -m pytest tests -q` → 44 passed  
- [ ] （可选）MySQL 查 `crm_lead` → **不应**因 503 产生新行  

---

## 8. 相关文档与产物

| 文件 | 用途 |
| --- | --- |
| `docs/dify/ENT-企业助手-Chatflow搭建清单.md` | 节点说明 + 应用 ID |
| `docs/dify/ent-workflow-graph.json` | 工作流图（v2） |
| `docs/回复Cursor/runs/ent-dify-acceptance-latest.json` | API + pytest 机器读报告 |
| `docs/回复Cursor/runs/ent-dify-workflow-runs-2026-11-12.json` | 4 条对话用例摘要 |
| `scripts/run_ent_dify_acceptance.py` | 可重复跑 I1～I4 |

---

## 9. 风险与后续（不阻塞「联调演示」）

1. **JWT 未接入前**：业务 HTTP 一律 503 —— Dify 演示以「链路通 + 错误话术正确」为验收标准。  
2. **要真入库**：需 `tests.repro` 或 auth 落地后改 Base URL / 鉴权头，并走客户 P2 回归。  
3. **OpenAPI 工具导入**：清单 §8 可继续减少手填 URL。  
4. **跟进/改状态/NL2SQL**：当前图仅覆盖 **录入 + 查询探路**，其余意图在 LLM 说明中，未接全部分支。

---

*本报告对应过夜交付；v2 同步后请在本文件末尾自行注明「v2 已发布」时间与复测结果。*
