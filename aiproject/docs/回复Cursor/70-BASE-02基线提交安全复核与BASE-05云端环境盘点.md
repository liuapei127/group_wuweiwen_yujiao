# 70 BASE-02 基线提交安全复核与 BASE-05 云端环境盘点

日期：2026-11-12  
结果：**基线提交复核未通过。** 发现硬编码数据库口令字面量后已停止，没有进入 BASE-05，没有改写 `26612581`，没有推送。

本报告不记录口令、密钥或 Token 原文。

## 第一部分：Git 安全基线最终复核

### 1. 当前 Git 状态

| 项目 | 实测 |
| --- | --- |
| 当前分支 | `feature/base02-safe-baseline` |
| 当前 HEAD | `8515687ae8c20c59420a71b9cb78f3f5df016f0e` |
| 基线提交 | `26612581c818d3e99af07d6663c020bc05d268f7` |
| 69 号报告提交 | `8515687ae8c20c59420a71b9cb78f3f5df016f0e` |
| 暂存区 | 空 |
| 推送 | 没有 |

最近三个提交：

| 顺序 | Hash | 父提交 | 说明 |
| --- | --- | --- | --- |
| HEAD | `8515687ae8c20c59420a71b9cb78f3f5df016f0e` | `26612581c818d3e99af07d6663c020bc05d268f7` | BASE-02: record the local baseline acceptance. |
| 基线 | `26612581c818d3e99af07d6663c020bc05d268f7` | `177df8fa856d537c38e84a7bc77a378eb263d328` | BASE-02: establish reviewed project baseline. |
| 初始 | `177df8fa856d537c38e84a7bc77a378eb263d328` | 无 | Initial commit |

`8515687` 只在 `26612581` 之上增加验收报告和索引。`26612581` 是 `177df8f` 的直接子提交。`git merge-base --is-ancestor` 确认基线提交是当前 HEAD 的祖先。

`git status` 在复核当时是：

```text
## feature/base02-safe-baseline
?? backend/
?? docs/
?? 教育服务_0914/
```

这三个目录都还在磁盘上。`git ls-tree -r` 核对了基线提交的全部 449 个路径，其中没有 `backend/`、根目录 `docs/`、`教育服务_0914/`。这次没有修改这三个目录。

### 2. 对 449 个文件的内容扫描

扫描对象是提交 `26612581` 里的 blob，不是工作区副本。比对时只用哈希和出现次数，不输出原文。

| 检查项 | 结果 |
| --- | --- |
| 数据库文件 | 无 |
| SQL 数据备份 | 无。两份迁移文件只含 `CREATE TABLE`，没有 `INSERT` |
| 上传文件 | 只有 `aiproject/data/uploads/.gitkeep` |
| 日志 | 只有 `aiproject/logs/.gitkeep` |
| 缓存、构建产物 | 无 `__pycache__`、`dist`、`build`、`.pyc` |
| `node_modules`、虚拟环境 | 无 |
| 私钥块、AWS 密钥形态、带账号口令的 URL | 无 |
| 与当前 `AUTH_JWT_SECRET`、`AUTH_BEARER_TOKEN` 相同的字节 | 无 |
| 其他模块的真实凭据 | 未在这 449 个文件中发现另一组凭据字节 |

`aiproject/.env` 仍被 `*.env` 忽略。历史快照仍被 `*portal-env*`、`*credentials*.json`、`*dify-secret*.json`、`logs/*` 忽略。`aiproject/.env.example` 在提交内，数据库口令仍是占位符 `change_me`，`AUTH_BEARER_TOKEN` 为空，`EMPLOYEE_IDENTITY_MODE=blocked`。

`aiproject/.env` 的身份模式仍是 `blocked`。这次没有改该文件，没有改 MySQL 口令、账号或授权，也没有访问 8000。

### 3. 未通过项

下面两个已跟踪脚本各含有一处与当前本机 `DB_PASSWORD` 完全相同的字面量：

| 文件 | 出现次数 | 形态 |
| --- | --- | --- |
| `aiproject/scripts/_probe_db_conn.py` | 1 | 引号括起的 6 位数字，位于未设置环境变量时的候选列表 |
| `aiproject/scripts/run_customer_e2e.py` | 1 | 同样是引号括起的 6 位数字，位于同一类候选列表 |

这是硬编码的当前数据库口令，不是 `.env.example` 里的 `change_me`。因此 **69 号报告里的“真实凭据没有进入跟踪文件”不能维持。** 基线提交本身保留，不重置、不改写。

按本次约定，复核未通过就停止后续开发。没有修改这两个脚本，没有新建业务提交。

## 第二部分：BASE-05 腾讯云演示环境

**未开始。** 原因是第一部分没有通过。没有登录腾讯云，没有重启服务，没有改防火墙、云端文件或发布版本。

已有的 `aiproject/docs/回复Cursor/33-Python313环境调整与腾讯云升级.md` 和 `backend/docs/腾讯云部署与小组协作.md` 不是本轮新盘点，不能当作云端现状。

## 4. 建议的下一步

由项目负责人决定如何处理这两个脚本里的候选字面量。处理时应新建提交，不要改写 `26612581` 或 `8515687`。处理完成并再次复核通过之前，不进入 BASE-05。
