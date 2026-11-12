# 69 BASE-02 本地 Git 安全基线验收报告

日期：2026-11-12  
结果：**本地安全基线已经建立。** 没有推送，没有修改数据库口令，没有改 `aiproject/.env`。

数据库口令由项目负责人本人管理。口令保持不变，不阻塞后续代码开发。

## 1. 提交结果

| 项目 | 结果 |
| --- | --- |
| 分支 | `feature/base02-safe-baseline` |
| 父提交 | `177df8fa856d537c38e84a7bc77a378eb263d328` |
| 本次提交 | `26612581c818d3e99af07d6663c020bc05d268f7` |
| 说明 | `BASE-02: establish reviewed project baseline.` |
| 文件数 | 449 |
| 变更规模 | 91252 行新增，1 行删除 |
| 暂存区 | 空 |
| 推送 | 没有 |

本验收报告在基线提交之后另行提交，所以分支顶端会比 `26612581c818d3e99af07d6663c020bc05d268f7` 多一个只包含本报告和索引的提交。基线内容以 `2661258` 为准。

`origin` 仍是 `http://47.106.207.27:3000/0914/group_wuweiwen_yujiao.git`。没有修改远程地址，没有合并 `origin/common` 或 `origin/feature/muhetaer-stu`。

## 2. 纳入版本库的内容

- 根目录 `README.md` 的现有说明
- 根目录 `.gitignore`
- `.cursor/rules/base-implementation.mdc`
- `aiproject` 源码、前端、测试、迁移、脚本、文档和 `.env.example`
- `aiproject/AGENTS.md` 与 `aiproject/.gitignore`

## 3. 继续留在工作区、未纳入的目录

| 路径 | 原因 |
| --- | --- |
| `backend/` | 早期参考工程，不进这次基线 |
| 根目录 `docs/` | 组会和全系统说明，不是 `aiproject` 运行树 |
| `教育服务_0914/` | 原始需求和素材，体积大且含二进制 |

这三个目录仍是未跟踪状态，没有删除。

## 4. 排除在 Git 之外的敏感文件

提交后的跟踪列表里，环境文件只出现 `aiproject/.env.example`。`credentials.py` 是签名代码，不是凭据文件。

`git check-ignore` 确认这些路径被忽略：

| 路径 | 命中的规则 |
| --- | --- |
| `aiproject/.env` | `*.env` |
| `aiproject/logs/portal-env-before-ai-acceptance.env` | `*portal-env*` |
| `aiproject/logs/ent-portal-local-credentials.json` | `*credentials*.json` |
| `aiproject/logs/ent-portal-dify-secret.json` | `*dify-secret*.json` |
| `aiproject/logs/portal-before-002-20261112-122152/private-env-before.txt` | `logs/*` |

`.env.example` 不被忽略，其中的数据库口令仍是占位符 `change_me`。

本次还给两份 `.gitignore` 补上了 `*.env`、`private-env*.txt`、`*portal-env*` 和 `*dify-secret*.json`，避免历史快照以后换个位置就被提交。

## 5. 数据库口令边界

本次没有修改 MySQL 口令，没有修改 `aiproject/.env` 的 `DB_PASSWORD`，没有创建或修改数据库账号，没有改授权，没有执行口令轮换。报告和终端都不记录真实口令。

口令轮换仍由项目负责人决定。它不作为 BASE-02 本地基线的阻断条件，也不阻断后续业务开发。8000 继续保持 `blocked`，这次没有切换身份模式。

其他远程分支里的历史凭据不在本次提交中。没有改写那些分支的历史。

## 6. 尚未完成

- 向已确认的 HTTPS 或 SSH 地址推送。当前仍不推送。
- 远程分支保护证据。
- `backend/`、根目录 `docs/`、`教育服务_0914/` 是否另建提交。
- BASE-05 和统一身份编码。

## 7. 回滚

这个提交只存在于本地分支。若要撤回，另建一个反向提交，不要使用 `git reset --hard` 或 `git clean`。未跟踪的三个目录和被忽略的 `.env` 都要保留。
