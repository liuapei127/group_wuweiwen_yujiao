# ENT 增量迁移

001_ent_reliability：成绩考试/提交标识、版本、更正历史；来源待办唯一约束、分配修订号和通知去重标识。

从 aiproject 运行 python -m scripts.migrate_ent_reliability --apply。当前脚本仅允许本机数据库。MySQL DDL 隐式提交，不能承诺失败后一键事务回滚；脚本先检查来源待办重复数据，逐列/逐索引检查，可在排除错误后重新运行。迁移不删除或合并既有数据。

001_ent_reliability_expected.sql 是迁移后的表结构校验基准，不应作为覆盖已有表的部署脚本。local_ent_validation 在历史表存在时叠加此基准，当前预期共32表。

首次本地执行前的行级备份在 logs/ent-migration-001-before.json（git忽略）；原有行及原有列内容已核对保留。云端尚未执行；云端执行前需按该环境备份、确认版本并演练。

旧成绩同一学生、课程、学期只有一条时回填默认考试标识；若有多条则保留每条并使用 legacy:<原ID>，不自动判断哪条是重考或重复。历史表写入 baseline，之前的修改记录未知，不虚构。


## 官网集成增量迁移

已有原始业务表的 MySQL 8 环境先核对 customer_source.id 和 sys_user.id 为 BIGINT UNSIGNED，再备份数据库。按顺序应用 pending 下的 006、007、008、009、010、011。已有 customer_source/customer_profile 时沿用现有表。已有 event_lecture/event_registration 时使用 010，空白环境使用 005 建立活动表。两种活动迁移路径分别适用不同的初始结构。application_progress 沿用已有业务表。


## 学生助手会话与记忆

`pending/014_student_assistant.sql` 建立 `stu_assistant_conversation`、`stu_assistant_message`、`stu_mem0_memory`。旧版本由学生助手在首次请求时自动建表，014 接管这三张表后应用不再执行任何运行期 DDL；已建表的库重复执行为空操作。回退需要删除会话与记忆数据，因此未提供回退脚本，需要时先导出再手动 DROP。

## BASE 本地认证升级

本机已有员工认证表时，备份业务库，核对会话主键字符集及用户、组织主键，分别核对这些迁移是否已执行。缺失时按顺序应用 `pending/003_base_refresh_token.sql`、`pending/012_base_service_identity.sql` 和 `pending/013_base_organization.sql`。013 含 MySQL DELIMITER 段，使用 MySQL 客户端导入。应用 DDL 后再为实际组织管理员授予 `organizations:manage` 并为需要部门范围的主管登记已有组织成员。三个回退文件会移除新结构，执行前先保留当前数据备份。

## 官网栏目与卡片

已有数据库在员工角色表和权限表就绪后应用 `pending/016_website_content.sql`。迁移建立官网栏目和卡片表，将首页原有文案写入并为管理员授予官网内容管理权限。

## 智报中心

应用 `pending/015_reporting_board.sql` 后再启动新版工作台和扫描任务。迁移建立签约流失事件、员工周报、自评与关怀表。签约和流失从迁移之日开始记录。

## 官网客服会话

应用 `pending/017_customer_chat_session.sql` 后再启用官网客服的连续对话。会话保存最近问题、Dify 会话编号及已选活动，两个小时后失效。现有提醒扫描进程清理过期会话。预约仍写入原有活动预约表。

## 官网个人头像

启用官网个人信息及上传头像前应用 `pending/018_visitor_avatar.sql`。头像按官网账号独立保存，上传后统一转成 256 × 256 的 WebP。

## 活动发布状态

在已有活动表的环境应用 `pending/019_event_publication.sql` 后启动新版后端。迁移将现有活动的发布状态设为已发布，游客预约列表仍按开始时间和活动状态筛选。

## 官网注册昵称

应用 `pending/020_visitor_nickname.sql` 后启动新版后端。现有官网账号的昵称初始为空。

## 客户资料协同与研判

启动新版前应用 `pending/021_customer_workspace.sql`。本迁移补充共享资料版本、按客户保存研判快照、独立核验身份和短时导入预览。已有客户编号、游客关联和跟进记录继续使用。已核实的姓名及手机号由系统管理员在「官网账号」登记，历史账号按原值保留。
