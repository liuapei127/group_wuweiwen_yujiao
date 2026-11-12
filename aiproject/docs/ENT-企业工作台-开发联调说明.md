# ENT 企业工作台 · 开发联调说明

日期：2026-11-12。目录为frontend/，Vite + React + Ant Design，门户API为8002。

## 通道与端口

| 通道 | 入口 | 身份与AI方式 |
| --- | --- | --- |
| 员工门户 | http://127.0.0.1:5173 | JWT+实时RBAC；AI经后端AssistantService和私有portal intent workflow |
| 门户API | http://127.0.0.1:8002 | EMPLOYEE_IDENTITY_MODE=trusted_jwt，ASSISTANT_API_URL=http://127.0.0.1:8002 |
| 既有Dify Chatflow API | 8000 | 保留默认blocked及原拒绝场景；公开32节点图调用此端口 |

门户不嵌入Dify iframe。浏览器不持有Dify API Key，员工JWT不发送给Dify。私有Dify只抽取参数；写入前确认、取消、重复确认保护、RBAC及业务执行由后端负责。

## 首次初始化与启动

在aiproject目录执行：

    .venv313\Scripts\python.exe scripts\setup_ent_portal.py --bootstrap
    .venv313\Scripts\python.exe scripts\start_ent_portal.py

初始化只面向本机education_service，先备份，新增002迁移的七张扩展表和四角色合成联调账号，不重置原账号密码。私有凭据在logs/ent-portal-local-credentials.json，角色/样例编号摘要在data/datasets/ent-portal-local-manifest.json。

运行日志在logs/ent-portal-api.log及ent-portal-web.log，进程登记在logs/ent-portal-processes.json。需要重启本项目进程时使用start_ent_portal.py --restart；生产构建后可使用--production启动Vite预览，当前未由FastAPI静态托管。

私有Dify workflow DSL在docs/dify/ent-portal-intent-workflow.yml。DIFY_WORKFLOW_API_KEY配置在服务端.env；Dify需已启动且模型可用，不能用前端写死员工编号替代身份链路。

## 严格HTTP验收

    .venv313\Scripts\python.exe scripts\verify_ent_portal_http.py --output docs/回复Cursor/runs/ent-portal-http-latest.json

默认必须提供admin、employee、manager、team_leader四套不同且完整的账号。验收检查真实角色、login/me/context身份一致、权限集合、菜单集合、28项接口授权及退出后token=401。有效身份但无权限必须403，401不作为RBAC通过。

只想探活时显式使用--health-only；该结果scope为auth-readiness，不代表登录/RBAC通过。角色已自定义时，可用--expectations FILE提供四角色预期权限JSON，不能静默接受权限变化。

副作用：登录会新增认证会话和审计；脚本finally退出全部已获得的token并检查失效，审计记录仍保留。HTTP脚本不创建或修改客户、成绩等业务记录。

## pytest隔离验证

    .venv313\Scripts\python.exe -m pytest tests -q

门户测试显式控制配置并将get_db覆盖到内存SQLite，禁止连接生产引擎。blocked匿名context精确为503；trusted_jwt匿名精确为401。待办跨秒用例使用受控时间，确保同步新版本后本轮通知不会遗漏。

## 浏览器验收

先启动门户；验证真实AI时还需启动Dify并配置私有workflow密钥。然后在frontend目录执行：

    npm run test:e2e

默认包含三个项目，未就绪或后端500会失败，不会自动skip：

- ui-smoke：登录页面形态，不代表后端就绪。
- portal-integration：经5173代理检查ready及trusted_jwt；四角色登录、菜单/按钮差异、受限URL、接口403和退出失效。
- portal-ai：真实Dify参数理解、确认前无写入、取消、取消后确认、确认写入一条待办、重复确认不重写、AI查询返回该待办。

可分别运行npm run test:e2e:ui、npm run test:e2e:portal、npm run test:e2e:ai，记录实际项目范围，不能把仅UI通过说成全量通过。AI项目会保留一条标题为ENT-AI-E2E-时间戳的合成待办和对话记录，供追溯。

Windows本地默认复用已安装的Chrome浏览器程序，但使用全新隔离测试配置，不读取个人Chrome会话。CI默认使用Playwright Chromium（需先npx playwright install chromium）。可用ENT_E2E_CHANNEL=chrome或chromium显式选择。

设置ENT_PORTAL_URL后视为已运行的外部目标，不自动拉起本地Vite；默认本地目标为5173，CI不复用已有端口进程。ENT_PORTAL_API若明确设置，只增加独立后端直连检查，不能替代代理检查。

失败trace和截图保存在frontend/test-results，已忽略。trace可能含测试登录请求和令牌，保持私有，不提交或公开分享。

## 角色与范围

以rbac.py的初始ROLE_DEFAULTS及数据库实际授权为准。admin可见16个菜单；employee和manager均11个，但manager额外有联系方式和指南维护权限；班主任有成绩及请假页面，菜单12个。不能仅比较菜单数量；前后端path/permission映射需逐项一致。

云端统一部署、FastAPI静态托管、每台机器自动发布私有Dify工作流、完整CI基础设施仍属于后续环境工作，不据本地回归声称完成。
