# 68 BASE-02 本机 MySQL 口令轮换方案

日期：2026-11-12  
结果：**只读检查已完成，轮换方案已写好。还没有改数据库口令，没有改 `.env`，没有提交或推送。**  
本报告不记录当前口令，也不生成新口令。

Git 状态保持为：分支 `feature/base02-safe-baseline`，HEAD `177df8fa856d537c38e84a7bc77a378eb263d328`，暂存区空，没有新提交，没有合并 `origin/common` 或 `origin/feature/muhetaer-stu`。8000 继续保持 `blocked`，这次没有访问 8000。

## 1. 本机 MySQL

| 项目 | 结果 |
| --- | --- |
| 实例 | Windows 服务 `MySQL`，状态 Running，启动类型 Automatic。进程 `mysqld`，PID 6380 |
| 版本 | 8.0.27 |
| 数据目录 | `C:\tools\mysql\mysql-8.0.27-winx64\data\` |
| 端口 | 3306，`bind_address=*`，`skip_networking=0`。监听地址是 `::`，不是只绑在 `127.0.0.1` |
| MySQL X | 33060，绑定同样是 `*`，监听地址也是 `::` |
| 安装目录中的选项文件 | 只看到 `data\auto.cnf`，没有找到单独的 `my.ini` |
| 防火墙 | Domain、Private、Public 三个配置文件都是启用。这次没有逐条核对 3306 的放行规则 |
| 当前连接 | 两条 `root@localhost` 睡眠连接，库是 `education_service`；另有本轮检查自己的查询和事件调度器 |

账号只有 `root@localhost` 可以登录。插件是 `caching_sha2_password`，账号未锁定、口令未过期。它拥有全部全局权限，包括 `Super`、`File`、`Grant`、建账号和关闭服务。没有 `root@%`，也没有匿名账号。`mysql.infoschema`、`mysql.session`、`mysql.sys` 都锁定在 `localhost`。

因此：端口对所有网卡开放，但这个 root 账号只接受本机登录。远程直接用 root 登录会因主机不匹配而失败。本机上的任何进程，只要知道已泄露口令，仍然可以拿到全部权限。

Docker 里没有 MySQL。正在运行的是 Dify，数据库容器是 Postgres，`5432` 没有映射到宿主机。`aiproject/compose.api.yaml` 只把 API 映射到 `127.0.0.1:8000`，没有映射 3306。它引用的 `mysql` 服务不在当前这两份 Compose 文件里，目前也没有该 Compose 在跑。

## 2. 哪些地方在用这组账号

当前应用通过 `DB_PASSWORD` 进入 `Settings.db_password`，再拼进 SQLAlchemy 连接串。依赖这个变量的是 `aiproject` 进程和那些从环境读取 `DB_PASSWORD` 的脚本，包括 `apply_db_init.py`、`compare_schema_*.py`、`run_customer_*.py`、`_probe_db_conn.py`。脚本文件里没有写死口令。

正在运行、启动时会读 `aiproject/.env` 的进程：

| PID | 命令 | 处理 |
| --- | --- | --- |
| 31500 | uvicorn `127.0.0.1:8002` | 轮换后要重启，才会读到新口令 |
| 45892 | uvicorn `0.0.0.0:8000 --reload` | 轮换后要重启。身份模式保持 `blocked`，不改成 `trusted_jwt` |
| 31648 | Vite `127.0.0.1:5173` | 不直接使用数据库口令 |

`Settings` 有缓存。只改 `.env` 而不重启这两个 uvicorn，旧口令会留在进程里。

`compose.api.yaml` 在启动时把外壳的 `MYSQL_PASSWORD` 传成容器里的 `DB_PASSWORD`。当前没有这个容器，所以没有一份正在运行的容器配置要改。以后如果启动它，新口令只能从外壳临时传入，不能写进仓库。

`backend/.env` 不存在。`backend/.env.example` 仍是占位符 `your_password`。用户级和系统级环境变量 `DB_PASSWORD`、`MYSQL_PASSWORD` 都没有设置。

在 `D:\Project course`、`D:\Project` 以及用户目录浅层里，文件名是 `.env` 的配置中，只有 `aiproject/.env` 的 `DB_PASSWORD` 与已泄露口令相同。Dify 源码包里的示例口令不同。

同一台 MySQL 上还有这些业务库，它们没有单独的账号，都靠这一个 `root@localhost`：

`0924task`、`ai0914`、`day_01_test`、`demo`、`education_service`、`emp_db`、`ent_verify_reliability_0b51bb12`、`fast_api`、`gbk_db`、`product_management`、`student`、`student_management`、`test_db`、`zuoye`。

轮换 root 口令会同时影响这些库的后续新连接。当前没有在这些库名下找到另一份相同口令的 `.env`。

## 3. 轮换后必须更新的本地配置

只更新下面三处，都不进入 Git：

| 位置 | 原因 | 动作 |
| --- | --- | --- |
| `aiproject/.env` 的 `DB_PASSWORD` | 当前应用正在使用 | 改成新口令 |
| `aiproject/logs/portal-env-before-ai-acceptance.env` 的 `DB_PASSWORD` | 已核对为同一口令 | 改成新口令，或删除这份过期快照 |
| `aiproject/logs/portal-before-002-20261112-122152/private-env-before.txt` | `setup_ent_portal.py` 会把整个 `.env` 复制到这里 | 按含有旧口令处理，改掉或删除 |
| `C:\Users\Windows\.cursor\mcp.json` | 本机 MySQL MCP 配置里有同一口令 | 只改数据库口令字段 |

不改 `aiproject/.env.example`、`backend/.env.example`、`README.md`、报告和任何已跟踪文件。不把新口令写进聊天。

`logs/` 里还有 `ent-portal-local-credentials.json`、`ent-portal-dify-secret.json`。这次没有打开它们。执行轮换时只按字段名检查有没有 `DB_PASSWORD` 或 MySQL 口令；没有就不动。

## 4. 备份方法

仓库里没有现成的 MySQL 定时备份。`mysqldump.exe` 在 `C:\tools\mysql\mysql-8.0.27-winx64\bin\mysqldump.exe`。

`setup_ent_portal.py` 的备份会把整个 `.env` 复制进 `logs/`，不适合这次轮换。`backup_dify_runtime.py` 备份的是 Dify，不是这台 MySQL。

执行轮换前，用 `mysqldump` 导出上面列出的全部非系统库，放到仓库以外的目录。口令放在临时的 `defaults-extra-file` 里，用完即删，不出现在命令行、报告或仓库中。导出文件也不放进仓库。

这一步只保护数据。它不能从远程 Git 历史里去掉已经泄露的旧口令。

## 5. 轮换步骤

这次还没有执行。得到确认后再按这个顺序做：

1. 保持当前分支和未跟踪文件不动。8000 保持 `blocked`。
2. 按第 4 节在仓库外做逻辑备份。
3. 在仓库外的临时文件里生成新口令。不写入报告、Git、README 或聊天。
4. 执行 `ALTER USER 'root'@'localhost' IDENTIFIED BY` 新口令。不新建远程账号，不把 root 授权给 `%`。
5. 更新第 3 节的本地配置。
6. 重启 8002 和 8000。8000 仍使用 `blocked`，不切换身份模式，不改业务代码。
7. 用新口令做一次本机登录，并确认 `education_service` 还能读取。失败时修正本地配置，不把口令改回旧值。
8. 删除临时口令文件。
9. 不改写 `origin/common` 和 `origin/feature/muhetaer-stu` 的历史，也不向 HTTP 远程推送。

旧口令已经在远程历史里。轮换之后，旧口令只作为失效口令保留在那些历史提交中，不能再作为恢复手段写回数据库。

监听范围这次不一起改。若之后要把 MySQL 限制到本机，需要先确定生效的选项文件，把 3306 和 33060 都改为 `127.0.0.1`，再重启 MySQL。那会中断当前连接，要单独确认后再做。
