# ENT 企业智能工作台

官方Vite React/TypeScript脚手架，React19、Ant Design6、React Router7和TanStack Query5。业务源码位于src，门户API为8002，开发/预览入口为http://127.0.0.1:5173。

## 初始化与启动

在aiproject目录执行：

    .venv313\Scripts\python.exe scripts\setup_ent_portal.py --bootstrap
    .venv313\Scripts\python.exe scripts\start_ent_portal.py

账号密码在忽略的logs/ent-portal-local-credentials.json。管理员、员工、经理、班主任均使用真实登录和后端RBAC；菜单与按钮按permissions显示，数据还受本人归属及学生范围限制。

仅启动前端：

    npm install
    npm run dev

Vite代理/api及/health到8002。该API进程显式trusted_jwt；原8000的blocked进程保持独立。

构建及预览：

    npm run build
    npm run preview

## 验收

先启动API；完整AI验收还需本地Dify及服务端DIFY_WORKFLOW_API_KEY。测试项目如下：

    npm run test:e2e          # UI + 四角色RBAC + 真实AI，前置条件不足即失败
    npm run test:e2e:ui       # 仅登录页形态，不代表联调完成
    npm run test:e2e:portal   # 真实角色登录、代理、菜单/按钮、403、退出失效
    npm run test:e2e:ai       # AI确认/取消/重复确认 + 一条合成待办写入与查询

Windows本地可用已安装Chrome（独立测试配置，不使用个人会话）；CI使用Playwright Chromium，需先npx playwright install chromium。ENT_E2E_CHANNEL可显式设为chrome或chromium。

ENT_PORTAL_URL指定外部已启动目标时，Playwright不启动本地Vite。CI不复用已存在的本地服务器。ENT_PORTAL_API只增加独立后端直连检查，所有集成项目仍要经过前端代理验证。网络失败、HTTP500、错误mode或ready=false不会静默跳过。

测试登录会生成会话与审计，结束时退出会话；AI用例保留一条ENT-AI-E2E-*合成待办与对应对话。失败trace/截图保存在被忽略的test-results，可能包含测试凭据/令牌，不提交或公开。

## 页面与后端

| 路径 | 职责 |
| --- | --- |
| src/navigation.tsx | 权限菜单与页面入口 |
| src/pages/Business.tsx | 客户、日报、组织、指南、通知、查询、指令 |
| src/pages/Operations.tsx | 成绩、历史、请假、工单、待办 |
| src/pages/Administration.tsx | 员工账号、学生授权、角色权限、审计 |
| src/pages/Assistant.tsx | 后端持久化AI会话与确认卡片 |
| src/components/shared.tsx | 实际接口驱动的表格、表单与弹窗 |
| e2e | UI、四角色与AI回归；不混入业务src |

浏览器只访问/api/v1/ai/assistant/*；Dify密钥保留在服务端.env，私有参数工作流与公开ENT Chatflow分开。

完整说明见../docs/ENT-企业工作台-开发联调说明.md；修复记录见../docs/回复Cursor/60-门户验收加固与待办时序修复-2026-11-12.md。
