# 45 本地数据库与 ENT 测试数据使用说明

日期：2026-11-11。主目录：aiproject。

## 数据库检查结论

连接为本机 127.0.0.1:3306/education_service，MySQL 8.0.27；标准 SQL 中的 31 张表已存在。

本次逐表比较列名、列类型、可空性、默认值、自增、更新时间、主键/索引的名称/列/类型/唯一性，以及引擎与表排序规则，未发现差异。这是已列维度的结构检查，不表示全部业务和数据关联已验收；未验证 FULLTEXT 分词效果等语义。

没有重跑 db_init.sql。该文件包含 DROP TABLE，直接重跑会删除现有表数据，本次没有执行其建表或初始化语句。

## 新增测试数据

所有新增内容均为虚构数据，使用 ENT_LOCAL_VERIFY_V1 标记或专用用户/学生关联，邮箱使用 example.invalid。指南明确标注为演示资料，不是真实公司制度。

| 表 | 本轮新增 | 当前总数 | 覆盖场景 |
| --- | ---: | ---: | --- |
| sys_user | 6 | 6 | 两名正常员工、一名停用员工；两名正常学生、一名停用学生 |
| sys_organization | 4 | 4 | 公司、两个部门、停用部门 |
| onboarding_guide | 4 | 4 | 三条启用演示指南、一条停用指南 |
| student_info | 3 | 3 | 学生与班主任关联、正常/暂停学籍 |
| crm_lead | 8 | 27 | 五种销售状态、本人同名客户、他人客户 |
| crm_follow_up | 4 | 9 | 员工与客户关联的虚构跟进 |
| employee_daily_report | 4 | 4 | 两名员工各两天日报 |
| student_score | 4 | 4 | 不同学生、课程、精度及停用学生历史成绩 |
| student_admin_service | 6 | 6 | 本人/他人/未分配审批人，待处理/已同意/已拒绝，同一学生多单 |
| student_feedback_ticket | 6 | 6 | 四种工单状态，他人指派、未分配 |
| todo_item | 5 | 5 | 到期/未来，待处理/处理中/完成/取消，他人待办 |
| notification_log | 3 | 3 | 两名员工站内通知隔离 |

合计新增 57 条。原有 19 条客户、5 条跟进、5 条角色和 20 条意图配置保留；种子写入前后对原有行内容进行了摘要核对，未改变。角色和意图配置没有新增。

## 主要编号

| 身份/数据 | ID |
| --- | --- |
| 验证顾问甲 | 1000001 |
| 验证顾问乙 | 1000002 |
| 停用员工 | 1000003 |
| 验证学生甲 | 1000004 |
| 验证学生乙 | 1000005 |
| 停用学生 | 1000006 |
| 甲名下新客户 | 20 |
| 甲名下同名客户 | 25、26 |
| 乙名下客户 | 27 |
| 甲学生两条成绩 | 1、2 |
| 甲待审批请假 | 1、6 |
| 乙待审批请假 | 2 |
| 未分配请假 | 3 |
| 甲待处理投诉 | 1 |
| 乙待处理投诉 | 5 |
| 甲到期待办 | 1 |

完整标识、所有记录 ID 和逐表新增数量见 data/datasets/ent-local-verify-v1-manifest.json。

最初空人员表的自动编号与旧客户负责人 1、2 重合，复查后已将本批六个人员调整至 1000001～1000006，仅同步本批关联数据，未改变旧客户。补数工具也已加入编号隔离逻辑。

## 如何检查和验证

从 aiproject 目录执行（PowerShell）：

~~~powershell
# 只读检查，不补数据
./.venv313/Scripts/python.exe -m scripts.local_ent_validation

# 补齐同一批数据并运行真实本地 MySQL 验证
./.venv313/Scripts/python.exe -m scripts.local_ent_validation --seed --verify --date 2026-11-11
~~~

补数按确定性标识检索，已存在则保留，不覆盖修改后的测试记录；重复运行已验证新增 0 条。若手动改变样例状态，后续固定初始状态断言可能失败，工具不会自动重置数据。

在数据库客户端可运行：

~~~sql
SELECT id, username, real_name, user_type, status
FROM sys_user WHERE username LIKE 'ENT_LOCAL_VERIFY_V1_%';

SELECT id, customer_name, owner_employee_id, status
FROM crm_lead WHERE remark LIKE 'ENT_LOCAL_VERIFY_V1:%';

SELECT id, student_id, course_name, score, semester
FROM student_score WHERE student_id IN (1000004,1000005,1000006);

SELECT id, student_id, status, approver_id
FROM student_admin_service WHERE reason LIKE 'ENT_LOCAL_VERIFY_V1:%';

SELECT id, title, assignee_id, status
FROM student_feedback_ticket WHERE title LIKE 'ENT_LOCAL_VERIFY_V1:%';
~~~

人员记录没有可用登录密码，不是可直接登录的账号。正常应用认证仍为 blocked/503；本地验证只在独立 FastAPI 实例中覆盖身份，未修改 app.main 的身份逻辑或对外放行。

## 已执行验证

29 项真实本地 MySQL + 隔离 ASGI 检查通过，包括组织/指南过滤、成绩读写及更正、客户权限与状态/跟进、同名冲突、日报、请假审批与重复提交、投诉流转与陈旧状态、待办、通知隔离、扫描与重复扫描去重，以及正常入口身份拒绝。

接口写操作和扫描均包在外层事务里，通过 SAVEPOINT 容纳业务 commit，结束后回滚；再次逐行核对已存在数据及 ID 集合，确认没有留下验证插入或状态修改。因此留给你的仍是初始样例状态。MySQL 自增序号可能因回滚产生间隔，这是正常现象。

原项目标准命令 python -m pytest tests -q：30 passed，保留一条既有 Starlette/httpx 弃用提示。一次额外 -X utf8 调用因父子 Python 编码设置不一致导致子进程输出解码失败，未修改源码，改用标准命令通过。

29 项真实 MySQL 场景和 30 项隔离 pytest 回归是不同验证集合，不表述为 59 项独立单元测试。没有验证真实 JWT、Dify、真实 TCP 或 MySQL 多工作进程并发；没有部署云端或启动提醒常驻任务。

归档证据：44-本地数据库检查与ENT测试数据.json；每次脚本执行的最新结果：runs/local-ent-validation-latest.json。

## 保留的历史数据缺口

原有 19 条客户分别引用员工 1（12 条）和 2（7 条），但 sys_user 无对应人员。这一关联缺口在本轮补数前已存在；本次不编造这两名旧负责人、不把历史客户改归测试顾问，保留原状。它不影响已建表的结构结论，但应在后续整理旧测试数据时处理。
