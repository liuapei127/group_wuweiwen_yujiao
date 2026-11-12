# 42 ENT 按统一框架重构与后续开发约定

日期：2026-11-11。用户已授权重构，并要求后续代码遵循提供的目录框架。

## 结果

已按框架调整当前 ENT 本地代码，不改变原有 HTTP 契约。主目录仍为 aiproject；backend 没有作为本次交付修改入口。

- enterprise_support 中的组织、新人、成绩、投诉、待办功能分别拆为 organization、onboarding、score、feedback、todo。
- 五个模块均有 router.py、schemas.py、models.py、repository.py、service.py。SQL 在 repository；业务权限、状态流转和事务在 service；router 绑定参数、调用 service、返回响应。
- enterprise_ops 的指令逻辑移入 service.py，HTTP 响应保留在 router；它不拥有独立表，不创建虚假 models/repository。
- core/config.py、database.py、responses.py 改为同名目录，原导入路径保持可用。
- 员工身份实现入口移至 core/security。core/auth 通过重导出保留同一函数对象，保证既有依赖覆盖不会失效。可信认证仍默认拒绝。
- 新 service 使用 BusinessError，公共处理器输出原有状态码和错误格式；CommandResult 由指令 router 转为响应。
- 新增 model_registry.py，在 main 启动装配中注册已实现模型。只导入模型，不建表、不迁移、不连接数据库。
- NL2SQL 新增 access.py，集中绑定可信员工范围；白名单和参数验证仍在 security.py。
- tests 按 modules、ai、integration、e2e 分类；原有 SQLite/ASGI 测试移入 integration。tests/repro 继续作为隔离复现工具。
- 补齐目录框架要求的其余包和数据目录。未实现部分明确为占位，不代表 LLM、Agents、RAG 等功能完成。

## 兼容路径

enterprise_support/router.py 仅聚合新业务路由，生产 registry 直接注册各业务模块，避免重复注册。tables.py 和 reminders.py 仅重导出新位置。旧脚本可以继续导入原符号，新代码不得继续往旧模块堆业务。

既有 consultant、employee_report、student_admin 的业务实现和接口保持。更细的既有事务惯例没有在本次整体重写，不能将本次目录重构描述为全项目代码质量或生产验收。

## 后续开发约定

开发规则已写入 aiproject/AGENTS.md；具体结构见 docs/architecture.md；用户原始框架存档为 docs/目录框架需求-2026-11-11.md。后续任务在该目录内开发时应先遵循这些约定。

允许按真实业务补充模块，但要更新架构说明。框架示例中尚无代码的其他团队模块只预留目录，不能由此承诺其他成员功能已完成。

## 验证

- 重构前：30 passed。
- 最终重构后：30 passed，退出码 0；仍有原有一条 Starlette/httpx 弃用提示。
- 重构前后完整 OpenAPI JSON 相同，22 个路径不变；请求字段、schema、operationId 与声明响应没有变化。快照保存在 runs/ent-refactor-openapi-before.json 和 after.json。
- 五个新增领域的分层静态检查通过；模型重复注册不增加或重复定义表。
- 最终 wheel 构建与临时目标目录安装成功；Python -I 从项目目录外导入安装包成功，应用包含 22 个路径与 11 张已实现映射，兼容对象身份与业务异常处理器检查通过。
- 初次无隔离 wheel 构建因本地环境没有 setuptools 构建后端而失败；改用 pip 默认隔离构建成功，没有为此改变项目业务依赖。

完整命令输出、契约摘要、源码 SHA256 及限制见 43-ENT目录重构验证记录.json。

## 未改变的项目待办

本轮不表示公共认证、真实 MySQL 并发、Dify、STU/RPT 联调或腾讯云验收已完成。没有执行共享库建表/迁移/清库，没有启动提醒常驻任务，没有发布云端或重建 Docker 镜像。旧阶段证据继续只绑定其当时版本，当前重构使用本次新证据。

后续阅读顺序：42 → docs/architecture.md → 43 → 当前源码；业务需求背景仍参考 40、39，源码位置以本次说明为准。
