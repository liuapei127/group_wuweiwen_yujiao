# ENT 企业助手 Chatflow（v3 修复版）

控制台：[企业智能助手-ENT](http://127.0.0.1:8088/app/ac18cfb8-3f60-406f-99dd-d9cc635dc71f/workflow)。API 为 http://127.0.0.1:8000，容器使用 http://host.docker.internal:8000。

## 配置来源

- 导入文件：ent-workflow-v3-fixed.yml（JSON 格式的有效 YAML DSL）。
- 当前规范图：ent-workflow-graph.json，与 ent-workflow-v3-fixed.json 一致。
- 参数、动作和结果契约：app/ai/workflows/ent_contracts.py。
- 修改契约后运行 Python 模块 scripts.build_ent_chatflow，生成 DSL 并同步规范图；运行 tests/ai 和 scripts.review_dify_graphs 检查，再在 Dify 草稿验证并发布。
- browser_sync_workflow.js 已停用。历史 v1/v2 保留在 archive，仅供排查。

## 执行规则

32 节点覆盖 27 个动作，包括客户、日报、组织、指南、成绩、请假、工单、待办、通知和白名单查询。流程为健康检查、模型抽取 JSON、代码验证、会话变量保存、固定 HTTP 方法和实际结果处理。

缺字段先追问；客户姓名查询后要求选择编号；写入前展示字段并要求明确确认。取消和重复确认不会再次提交。成绩更正带 expected_version。禁止模型决定成功结果或直接执行 SQL。

员工身份来自后端可信认证。不要添加固定 employee_id、伪造员工请求头或把数字当 Bearer token。actor 字段省略时由后端从已验证 principal 推导；未接入可信身份时默认返回 503。

HTTP 200、业务 code=0 和写入记录 id 一起满足才能说明成功。HTTP 503、403、409、422、404 与网络故障分别处理；写请求不自动重试。Dify 的 HTTP 异常分支会保留 partial-succeeded 状态，这是处理预期拒绝后的平台记录，不能当作业务写入成功。

## 验证

- .venv313/Scripts/python.exe -m pytest tests -q
- .venv313/Scripts/python.exe -m scripts.review_dify_graphs
- scripts.local_ent_validation：本机 MySQL 隔离事务业务验证。
- scripts.verify_ent_concurrency：ent_verify_ 独立库的多进程验证。
- scripts.dify_runtime_review：实际 Dify 草稿执行并检查节点轨迹。
- scripts.dify_published_review：已启用 WebApp 的普通 HTTP/SSE 多轮执行。

草稿和 WebApp 用例在 repair-dialogue-all.json。基础探活脚本 scripts.run_ent_dify_acceptance 只验证基础设施，不能替代上述对话或真实身份写入验收。

当前语音、真实员工 JWT、未确认的主管数据范围规则仍需后续接入；不要据目录占位声称这些能力已完成。

## 本机运行环境

使用 D:/tools/dify-1.16.0/docker 中的 dify 项目。已设置 COMPOSE_PROJECT_NAME=dify，重复 docker 项目已停止并关闭自动重启，以免两个 PostgreSQL/Redis 实例共享同一数据目录。

Redis 原 dump.rdb 损坏，已备份并保留原文件，恢复实例使用新快照名 ent-recovered-20261112.rdb；旧缓存/登录会话未恢复。PostgreSQL 逻辑备份保存在本项目忽略的 logs 目录。运行时 override 的无密钥示例为 runtime-recovery.override.example.yaml。
