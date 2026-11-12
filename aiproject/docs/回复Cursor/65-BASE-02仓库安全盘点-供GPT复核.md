# 65 BASE-02 仓库安全盘点（供 GPT 复核）

日期：2026-11-12  
阶段：BASE-02 的只读安全盘点。没有建立新的提交基线，没有推送。  
64 号架构文件没有改写。8000 仍保持 `blocked`。

## 1. 本阶段做了什么

| 项 | 结果 |
| --- | --- |
| 远程连接 | `git fetch origin` 成功。远程是 `http://47.106.207.27:3000/0914/group_wuweiwen_yujiao.git`。Git 提示该地址是未加密 HTTP |
| 本地分支 | 只有 `main`，提交 `177df8f`，说明为 Initial commit。与 `origin/main` 相同 |
| 已跟踪文件 | 只有仓库根目录的 `README.md`，且工作区里有未提交修改 |
| 未跟踪目录 | `aiproject/`、`backend/`、`docs/`、`教育服务_0914/`，以及根目录 `.gitignore`、`.uvicorn_test_pid.txt` |
| 敏感文件抽查 | `aiproject/.env` 存在，已被忽略。`aiproject/logs/ent-portal-local-credentials.json` 存在，已被忽略。两份 `.env.example` 只有占位值。`app/core/security/credentials.py` 是源码，没有被忽略 |
| 忽略规则 | 补了 `.env.*`、`*.pem`、`*.key`、`*credentials*.json`，并保留 `.env.example`。根目录另忽略 `.uvicorn_test_pid.txt` |
| 编码约束 | 写入 `aiproject/AGENTS.md` 和 `.cursor/rules/base-implementation.mdc`。内容是本地 Cookie 例外和组织历史的实施约束 |

没有执行 `git add`，没有提交，没有推送，没有切换或覆盖 `main`、`develop`、`common`。

## 2. 远程分支

| 分支 | 本次看到的提交 | 树的内容 |
| --- | --- | --- |
| `origin/main` | `177df8f` Initial commit | 与本地 `main` 相同 |
| `origin/develop` | `a94089b` Revert initialize-project-structure | 撤销后只剩 `README.md`。它的上一笔 `0646436` 曾在根目录放了 `app/`、`deployment/`、`docs/`、`frontend/`、`scripts/` |
| `origin/common` | `39446c0` 公共底座文档 | 根目录有早期公共底座文件：`main.py`、`security.py`、`config.py`、`database.py` 等，以及 `.env.example` 和 `公共底座文档.md` |
| 其他 | `origin/feat_智报`、`origin/feature/muhetaer-stu` | 本次只确认远程有这两个分支，没有检出，也没有比较文件 |

本地正在使用的代码在未跟踪的 `aiproject/`。它和 `develop`、`common` 的根目录布局不是同一棵树。把 `aiproject/` 提交进 `main`，或和这两个远程分支直接合并，都会把不同布局叠在一起。这次没有这样做。

## 3. 可以入库和必须排除

可以进入后续基线的是源码、测试、文档、前端源码，以及只含占位值的 `.env.example`。

必须继续排除：

- `aiproject/.env`、`backend/.env`，以及 `.env.local` 这类真实环境文件。
- `aiproject/logs/` 中的门户凭据和运行日志。
- `.venv313/`、`frontend/node_modules/`、构建产物、上传目录。
- 私钥 `*.pem`、`*.key`。
- `.uvicorn_test_pid.txt`。

`git check-ignore` 已确认：`.env` 和门户凭据 JSON 被忽略，`.env.example` 不被忽略，`credentials.py` 不被忽略。

## 4. 回滚位置

当前可回滚点是本地 `main` 的 `177df8f`。未跟踪的 `aiproject/` 还不在 Git 里，不能靠这次盘点做 Git 回滚。忽略规则和编码约束的修改也还没有提交。

## 5. 建议的下一步，尚未执行

确认后才做，并且仍不推送：

1. 从当前 `main` 新建功能分支，不在 `main`、`develop`、`common` 上提交。
2. 只暂存已经核对过、且没有被忽略的文件。禁止 `git add .`。
3. 做一次本地提交，作为 `aiproject` 的安全基线。
4. 提交前再跑一次 `git check-ignore` 和 `git status`，确认 `.env`、凭据和私钥不在暂存区。

BASE-02 还不能验收。缺的是：分支规范下的实际提交、不含密钥的基线，以及远程分支保护是否存在的证据。BASE-05 和统一身份编码都还没开始。

## 6. 本阶段文件

| 文件 | 变更 |
| --- | --- |
| `.gitignore` | 补充私钥、凭据和进程文件的忽略规则 |
| `aiproject/.gitignore` | 补充 `.env.*`、私钥和凭据忽略，并保留 `.env.example` |
| `aiproject/AGENTS.md` | 增加两条编码约束 |
| `.cursor/rules/base-implementation.mdc` | 同上，供后续编码会话使用 |
| 本文件 | 供复核的盘点记录 |

没有数据库变更，没有运行会写业务数据的测试，没有修改认证、生产配置和 Dify 工作流。
