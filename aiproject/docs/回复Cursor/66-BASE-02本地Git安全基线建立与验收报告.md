# 66 BASE-02 本地 Git 安全基线建立与验收报告

日期：2026-11-12  
结果：**本地提交已停止。** 历史提交里发现凭据类内容。按约定没有暂存、没有建立新提交、没有推送。  
没有修改业务代码、数据库、生产配置和 Dify 工作流。64 号架构文件没有改写。

## 1. 分支创建结果

已从当时的 `main`（`177df8f`）创建本地分支 `feature/base02-safe-baseline`。没有在 `main`、`develop`、`common` 上提交。没有切换到这两个远程分支，没有删除或覆盖工作区文件，没有动数据库。

当前分支就是 `feature/base02-safe-baseline`。它还没有新提交，HEAD 仍是 `177df8fa856d537c38e84a7bc77a378eb263d328`。

`README.md` 的现有修改还在，没有暂存，也没有丢弃。这段修改是在说明 `aiproject/` 为主目录、`backend/` 为早期参考，与基线有关，但因为本次提交中止，它仍留在工作区。

## 2. 本应纳入、但尚未纳入 Git 的范围

这些目录和文件已经看过与当前工程的关系。因为提交中止，它们都还是未跟踪或未暂存状态。

| 路径 | 关系 | 计划 |
| --- | --- | --- |
| `aiproject/` 源码、`frontend/src`、`tests/`、`aiproject/docs/`、`migrations/`、`scripts/`、`.env.example` | 当前主工程 | 敏感复查通过后再逐项纳入 |
| 根目录 `.gitignore`、`aiproject/.gitignore`、`aiproject/AGENTS.md`、`.cursor/rules/base-implementation.mdc` | 本次安全规则和编码约束 | 与源码同一基线纳入 |
| 根目录 `README.md` 的现有修改 | 说明主目录和早期目录的关系 | 不丢弃；提交恢复时一并纳入 |
| `backend/` | 早期 MVP，README 已写明逐步废弃 | 不纳入这次基线 |
| 根目录 `docs/` | 组会和全系统说明，不是 `aiproject` 运行树 | 不纳入这次基线 |
| `教育服务_0914/` | 原始需求、建表脚本和素材，体积大且含二进制 | 不纳入这次基线 |

计划排除、且当前忽略规则已经挡住的内容：`.env`、`.env.*`（保留 `.env.example`）、`*.pem`、`*.key`、`*credentials*.json`、`logs/`、`data/uploads/`、`.venv*/`、`frontend/node_modules/`、构建产物、`.uvicorn_test_pid.txt`。

## 3. 排除的敏感文件

| 位置 | 类型 | 是否进入本次暂存 |
| --- | --- | --- |
| `aiproject/.env` | 真实环境配置，含数据库和密钥类变量 | 否，已被忽略 |
| `aiproject/logs/ent-portal-local-credentials.json` | 门户本地凭据 | 否，已被忽略 |
| `aiproject` 源码中的 `credentials.py` | 签名和校验代码，未发现硬编码密钥 | 尚未暂存 |
| 工作区源码、文档、示例配置 | 未发现私钥文件，也未发现带账号口令的数据库 URL | 尚未暂存 |

没有把任何真实密钥写入本报告。

## 4. 本地提交

**没有新的提交。** 因此没有新的提交 Hash，也没有提交文件数量。HEAD 仍是 `177df8fa856d537c38e84a7bc77a378eb263d328`。

停止原因：下面这些内容已经存在于已获取的远程历史中，不是本次工作区里的新文件。

| 位置 | 类型 | 所在分支 |
| --- | --- | --- |
| `modules/student_assistant/backend/.env.example` 的 `DATABASE_URL` | 连接串中带有用户信息 | `origin/feature/muhetaer-stu`，自 `d61d376` 起的相关提交 |
| 同一文件的 `JWT_SECRET` | 短密钥字段，文本里带有提示性词语 | 同上 |
| 仓库根 `.env.example` 的 `MYSQL_PASSWORD` | 长度为 6，没有占位提示词 | `origin/common` 的历史提交 `e4d5ff5` |
| 同一文件的 `JWT_SECRET_KEY` | 较长字段，文本里带有提示性词语，更像说明性占位，不把它当成已确认的随机生产密钥 | 同上 |

`aiproject` 当前工作区里没有这些文件。按「发现已提交的真实凭据就先停止」的要求，没有继续 `git add` 和 `git commit`。

处理建议，供确认后再做：

1. 不要向当前 HTTP 远程推送。
2. 若这些值曾经用于真实数据库或签名，由对应模块更换数据库口令和 JWT 密钥。本报告不代为更换。
3. 不要在未获仓库负责人同意时改写已经公开的提交历史。
4. 确认上述历史问题的处理方式后，再在 `feature/base02-safe-baseline` 上只暂存审查过的 `aiproject` 和安全规则文件。

## 5. 提交前后状态

提交前和现在相同，因为没有暂存、没有提交：

```text
## feature/base02-safe-baseline
 M README.md
?? .cursor/
?? .gitignore
?? aiproject/
?? backend/
?? docs/
?? 教育服务_0914/
```

`git check-ignore` 此前已确认 `aiproject/.env` 和门户凭据 JSON 被忽略，`.env.example` 不被忽略。这次没有把它们放进暂存区，暂存区是空的。

## 6. 远程仓库安全问题

当前 `origin` 仍是 `http://47.106.207.27:3000/0914/group_wuweiwen_yujiao.git`。没有修改这个地址，也没有推送。

核对结果：

- 3000 端口上的 HTTPS 请求没有完成握手，不能把该端口当成现成的 HTTPS Git 地址。
- 443 端口有 TLS 服务，证书不受本机信任，响应来自 `openresty/1.27.1.2`，返回 HTTP 200。这只能说明 443 上有一个 Web 服务，不能证明 Gitea 已经挂在这个地址。
- 22 端口可以建立 TCP 连接。这不能证明 Git over SSH 已经开通。

建议先向服务器管理员确认，再改远程地址。候选是 `https://` 上已经核对过证书名称的 Gitea 地址，或 `ssh://git@47.106.207.27/0914/group_wuweiwen_yujiao.git`。在确认之前继续使用现在的 HTTP 地址只做只读查询，不推送，也不在 URL 里放账号、口令或 Token。

远程分支保护没有核实，不能写成已经完成。

## 7. 尚未完成

- BASE-02 的本地安全基线提交。
- 分支保护证据。
- 把远程从 HTTP 换成已确认的 HTTPS 或 SSH。
- `backend/`、根目录 `docs/`、`教育服务_0914/` 是否另建提交，仍待单独决定。
- BASE-05 和统一身份编码尚未开始。
- 8000 继续保持 `blocked`。

## 8. 回滚方法

这次只多了一个指向 `177df8f` 的本地分支，没有新提交。若要去掉这个分支，先切回 `main`，再删除 `feature/base02-safe-baseline`。工作区里的 `README.md` 修改和未跟踪目录不要用清理命令删除。历史中的凭据文件不要在本机用强推改写。
