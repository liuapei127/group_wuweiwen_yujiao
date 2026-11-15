# 粤教 Dify 本机集成

已在 Dify 1.16.0 导入和发布，应用通过同机 FastAPI 调用。工作室 http://127.0.0.1:8090/apps ，公司官网 http://127.0.0.1:5173/website ，员工工作台 http://127.0.0.1:5173/login 。

| 模块 | 应用 | FastAPI 入口 / 使用方式 |
| --- | --- | --- |
| CS | 粤教CRM-客服 · 本机集成 | 官网客服，POST /api/cs/chat |
| STU | 留学学生助手 · 统一API | stu.yml 新薄壳：官网登录或传入 Bearer → POST /api/v1/student/assistant/run。业务请假/投诉/进度/心理在 FastAPI。旧 8001/api/stu 版见 stu-legacy-api-stu.yml。 |
| PF | 客户研判 · 本机集成 | 员工工作台 → 客户研判 → 运行 Dify 研判。改动见 pf-改动说明.md |
| RPT | 员工正式报告 AI 总结 · 本机集成 | 员工工作台 → 业务报表 → 日报提交 → 生成 AI 总结 |
| ENT | 企业智能助手-ENT | 员工工作台 → AI 助手。32 节点版已发布，服务端配置 DIFY_ENT_CHATFLOW_API_KEY。 |

CS 绑定本机四个知识库，分别是公司简介、常见问题、留学项目、政策入口。四个本地 UUID 绑定保存在 cs.yml，迁往另一工作区时重建并绑定。客服使用 36 节点版。推荐和活动分支只调用官网的公开目录接口。新应用 WebApp 开关关闭，应用密钥由 FastAPI 服务端使用。RPT 与客服使用本机 Dify 已配置的通义 qwen-plus，调用时依赖通义服务；PF 由代码节点给出结论，再检索研判规则，并由通义 qwen-plus 按这一位客户写顾问建议。STU 已发布 15 节点版（统一学生 API + 模型兜底），旧的六节点版与 `/api/stu` 接口不再作为联调入口。学生请假和投诉另可在官网表单办理。

顾问研判预览处理游客说明与有权限的可读附件。预览供顾问确认，原资料、初筛状态和建档流程仍由业务接口处理。RPT 只允许有 reports:formal:generate 和 reports:summary:read 的当前管理员或主管使用，主管受部门范围限制。本机已授予管理员正式报告权限。

密钥配置使用忽略跟踪的 aiproject/logs/integration-dify.local.json，进程信息在同目录 integration-processes.json。原则上继续使用当前本机应用；重启时从原有本地 .env 读取数据库和员工认证配置，为新进程传入工作流密钥，后端环回 8003，Vite 代理变量 ENT_DEV_API_URL=http://127.0.0.1:8003 。工作流副本不包含应用 API 密钥。

### CS 导入要点

1. 应用 `017_customer_chat_session.sql`。导入 `cs.yml` 时绑定公司简介、常见问题、留学项目和政策入口四个知识库，并配置通义 `qwen-plus`。这四个检索节点使用 Dify 的权重模式（语义 100%，关键词 0%）。如果更换为其他嵌入模型，绑定后在节点检索设置中同步更新向量权重的模型。
2. 设置 `cs_api_base` 为 Dify 容器能访问的 FastAPI 地址。本机集成使用 `http://host.docker.internal:8003`。正式部署按实际端口填写。
3. 官网客服在同一会话内承接 FAQ 和政策续问。游客可查询活动，登录后才能选场并确认报名。预约结果可在「我的预约」查看。
4. 官网公开资料和政策官方入口用于回答；交付包的测试问答、SQLite 库和服务密钥不导入生产。

### STU 导入要点

1. 在 Dify 导入 `stu.yml` 并发布 Chatflow；WebApp 建议关闭，密钥交给 FastAPI `STU_DIFY_API_KEY`。
2. 环境变量：`stu_api_base`（默认 `http://host.docker.internal:8000`）、可选 `stu_website_username` / `stu_website_password`（仅工作室控制台直连调试）。空令牌时会用这组账号登录，生产必须留空，否则官网漏传令牌会被当成该账号办理请假。
3. 开始节点输入：`student_access_token`、`history_json`。官网已配置 `STU_DIFY_API_KEY` 时，FastAPI `/api/v1/student/assistant` 会带上当前学生 Bearer 与历史调用本 Chatflow；Chatflow 再打 `/assistant/run`，避免套娃。
4. 未配置 `STU_DIFY_API_KEY` 时，官网助手直接走本地口语脑，不依赖 Dify。
5. 两个 HTTP 节点都不配 `retry_config`：`/assistant/run` 会真的提交请假和投诉，Dify 自动重试会重复写业务单据；失败由 FastAPI 回退本地口语脑，不靠流程重试。
6. 旧版 `stu-legacy-api-stu.yml`（8001 `/api/stu`）仅作归档，不要再当联调入口。
7. 画布最后一个分支是模型兜底：`取出口语回复` 之后先过 `是否需要模型兜底`，只有回复里出现「我在听」这类没接住内容的话才进 `模型兜底回答`（通义千问 qwen-plus）；有办理结果的回复原样走 `助手回复`，不会被改写。模型输出先经 `去掉思考段` 去掉推理段，再交给学生。因此 Dify 工作区必须配置可用的通义供应商，否则该分支会报错。
8. 规则仍然负责动作：请假、投诉、进度、考务、高危预警都由 FastAPI 判定和落库；模型只负责把没说清的话接住。高危话术不经过模型，直接由 FastAPI 返回安抚并写预警。

本机 HTTP 已验证官网讲座指引、认领顾问可查看研判且其他员工拒绝、正式日报调用 Dify 返回四字段。ENT 32 节点版已验证查待办、取消、确认后只写入一次和重复确认拦截。合成业务数据已清理。STU 新 DSL 以统一学生 API 为准；旧 `/api/stu` 联调说明作废。

ENT 的 Chatflow 配置见 ent.yml。Dify 负责探活和指令抽取，员工令牌、确认、权限及业务执行由工作台后端处理。WebApp 已关闭。未配置新 Chatflow 密钥时，可用 DIFY_WORKFLOW_API_KEY 连接独立的参数理解工作流。

员工日报的录音转写使用 Dify 的语音转文字 API。在 Dify 配置默认语音转文字模型，并在用于转写的应用中启用语音转写后发布。配置 DIFY_REPORT_TRANSCRIPTION_API_KEY 可指定该应用，留空时使用企业助手 Chatflow 密钥。浏览器在 HTTPS 或本机地址录音。

ENT 32 节点版和 3 节点备用工作流使用同一动作目录。更新后依次运行 python -m scripts.build_ent_chatflow、python -m scripts.build_portal_intent_workflow 和 python -m scripts.refresh_ent_portal_chatflow，最后一步需要 PyYAML。部署时导入 local-integration/ent.yml 和 ent-portal-intent-workflow.yml。工作台「AI 助手」中的录音经 FastAPI 使用已有 Dify 语音模型，确认发送后才进入意图提取。

智报中心的投诉摘要、心理群体建议和员工报告比对可复用 RPT 工作流。更新 `rpt.yml` 并发布后，沿用现有 `DIFY_EMPLOYEE_FORMAL_API_KEY`。若完整配置 `REPORTING_LLM_*` 则优先使用独立模型。
