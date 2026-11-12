# 项目开发约定

用户已于 2026-11-11 确认后续代码遵循 docs/architecture.md 中的目录和分层约定。

- 当前交付主目录为本目录 aiproject；backend 为历史参考。
- Python 使用 3.13.x。
- 业务放 app/modules/<业务域>/；AI 能力放 app/ai/；公共设施放 app/core/；无业务依赖的通用代码放 app/shared/。
- 每个实际业务模块按 router.py、schemas.py、models.py、repository.py、service.py 分层。router 只处理 HTTP 输入输出并调用 service；禁止在 router 中直接执行 SQL、提交事务或实现状态机。schemas 定义请求/响应；models 定义表；repository 负责数据访问；service 负责业务、授权和事务编排。
- 新增路由统一在 app/router_registry.py 注册；新增表模型在 app/model_registry.py 注册。模型注册不得执行建表或迁移。
- 按业务域扩展模块允许，但必须更新架构文档；成绩统一放 score。不要把不同业务重新堆入 enterprise_support。
- core/auth 和 modules/enterprise_support 仅保留旧导入的兼容层，新代码使用所属业务模块及 core/security。
- tests/modules 放模块测试；tests/ai 放 AI 测试；tests/integration 放跨层/隔离 ASGI 测试；tests/e2e 放真正的端到端测试。tests/repro 仅用于隔离漏洞复现，禁止生产入口引用。
- 保留已发布 API 的地址、请求字段、响应和权限边界；需要变更契约时说明影响并补相关验证。
- 可信认证未实现前继续默认拒绝；不要恢复不可信员工请求头放行。权限和学生范围由可信服务端提供。8000 在安全验收清单通过前保持 blocked。
- 本地环回若必须关闭 Cookie 的 Secure：CSRF 与 Refresh 都不用 `__Host-`、`__Secure-` 前缀，并改用仅限本地的 Cookie 名。非环回环境禁止关闭 Secure。生产环境始终使用原定前缀和属性。
- 组织历史只记录一次。操作者只取自可信后端上下文，不接受前端传入。连接池不得把操作者留到下一个请求。过期清理要可事务、可并发、可重复执行。授权每次实时检查有效期，不依赖清理任务是否已跑。
- 不因重构连接共享库、清库、自动建表、运行迁移、启动扫描常驻进程或部署云端。此类操作按具体任务和环境处理。
- 预留目录和文件不表示业务已实现；不要编造组织数据、公司制度或未确认的业务规则。
- 修改后在本目录运行 .venv313/Scripts/python.exe -m pytest tests -q；按改动补充必要验证，区分隔离测试、真实 MySQL、真实身份、Dify 和云端验收。

- 无独立持久化的编排/健康检查模块无需创建虚假的 models/repository。新业务 service 使用 core/exceptions.BusinessError，HTTP 映射由公共异常处理器及 router 完成。
