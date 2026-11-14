# 粤教 Dify 本机集成

已在 Dify 1.16.0 导入和发布，应用通过同机 FastAPI 调用。工作室 http://127.0.0.1:8088/apps ，公司官网 http://127.0.0.1:5193/website ，员工工作台 http://127.0.0.1:5193/login 。

| 模块 | 应用 | FastAPI 入口 / 使用方式 |
| --- | --- | --- |
| CS | 粤教CRM-客服 · 本机集成 | 官网客服，POST /api/cs/chat |
| STU | 留学学生助手 · 统一API | stu.yml 新薄壳：官网登录或传入 Bearer → POST /api/v1/student/assistant/run。业务请假/投诉/进度/心理在 FastAPI。旧 8001/api/stu 版见 stu-legacy-api-stu.yml。 |
| PF | 客户研判 · 本机集成 | 员工工作台 → 游客跟进 → 材料详情 → 运行 Dify 研判 |
| RPT | 员工正式报告 AI 总结 · 本机集成 | 员工工作台 → 业务报表 → 日报提交 → 生成 AI 总结 |
| ENT | 企业智能助手-ENT | 员工工作台 → AI 助手。32 节点版已发布，服务端配置 DIFY_ENT_CHATFLOW_API_KEY。 |

CS 绑定本机四个知识库，分别是公司简介、常见问题、留学项目、政策入口。四个本地 UUID 绑定保存在 cs.yml，迁往另一工作区时重建并绑定。客服对课程和预约给出官网操作入口。新应用 WebApp 开关关闭，应用密钥由 FastAPI 服务端使用。RPT 与客服使用本机 Dify 已配置的通义 qwen-plus，调用时依赖通义服务；PF 研判在本地代码节点执行。STU 已发布组员原版六节点，旧接口待适配。学生请假和投诉仍可在官网表单办理。

顾问研判预览处理游客说明与有权限的可读附件。预览供顾问确认，原资料、初筛状态和建档流程仍由业务接口处理。RPT 只允许有 reports:formal:generate 和 reports:summary:read 的当前管理员或主管使用，主管受部门范围限制。本机已授予管理员正式报告权限。

密钥配置使用忽略跟踪的 aiproject/logs/integration-dify.local.json，进程信息在同目录 integration-processes.json。原则上继续使用当前本机应用；重启时从原有本地 .env 读取数据库和员工认证配置，为新进程传入工作流密钥，后端环回 8003，Vite 代理变量 ENT_DEV_API_URL=http://127.0.0.1:8003 。工作流副本不包含应用 API 密钥。

### STU 导入要点

1. 在 Dify 导入 `stu.yml` 并发布 Chatflow；WebApp 建议关闭，密钥交给 FastAPI `STU_DIFY_API_KEY`。
2. 环境变量：`stu_api_base`（默认 `http://host.docker.internal:8000`）、可选 `stu_website_username` / `stu_website_password`（工作室直连调试）。
3. 开始节点输入：`student_access_token`、`history_json`。官网已配置 `STU_DIFY_API_KEY` 时，FastAPI `/api/v1/student/assistant` 会带上当前学生 Bearer 与历史调用本 Chatflow；Chatflow 再打 `/assistant/run`，避免套娃。
4. 未配置 `STU_DIFY_API_KEY` 时，官网助手直接走本地口语脑，不依赖 Dify。
5. 旧版 `stu-legacy-api-stu.yml`（8001 `/api/stu`）仅作归档，不要再当联调入口。

本机 HTTP 已验证官网讲座指引、认领顾问可查看研判且其他员工拒绝、正式日报调用 Dify 返回四字段。ENT 32 节点版已验证查待办、取消、确认后只写入一次和重复确认拦截。合成业务数据已清理。STU 新 DSL 以统一学生 API 为准；旧 `/api/stu` 联调说明作废。

ENT 的 Chatflow 配置见 ent.yml。Dify 负责探活和指令抽取，员工令牌、确认、权限及业务执行由工作台后端处理。WebApp 已关闭。未配置新 Chatflow 密钥时，可用 DIFY_WORKFLOW_API_KEY 连接独立的参数理解工作流。
