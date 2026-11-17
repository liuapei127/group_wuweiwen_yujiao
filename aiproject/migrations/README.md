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


## 系统管理员和业务角色权限

应用 `pending/022_role_responsibilities.sql` 更新已有授权。系统管理员保留员工账号、角色、组织关系、审计、官网账号与内容、课程和活动管理。官网账号可核验客户身份，并在开通学生身份时建立或关联学生档案。顾问角色可认领游客和补录资料，主管角色可查看统计并生成正式报告，报表数据范围由「员工管理 → 组织关系」中配置的负责组织和成员决定。迁移可重复执行，业务数据和记录归属继续使用原值。

## 项目班级和班主任

班级与老师管理需在启动新版前依次应用 `pending/023_project_classes.sql` 和 `pending/025_class_teacher.sql`。025 仅执行一次，将既有班级原来继承的班主任保存到各班级。管理员在项目设置中配置留学地区，建班时为每班指定一名班主任。客户首次开通学生身份时须选择项目和班级，学生归属所选班级的班主任。同项目的不同班级可以由不同老师负责。已有学生的班主任归属继续使用其档案值，等待实际班级信息确认。

## 已认领游客的意向客户记录

部署后使用服务相同的数据库配置执行 `python -m scripts.backfill_claimed_customers`。脚本为历史已认领且没有客户记录的游客建立归原顾问所有的意向客户，保留认领日期并同步历史联系记录。已有客户、学生档案和已建立的关系按原编号继续使用。脚本可重复执行。

## 新加坡项目升学路径

应用 `pending/024_singapore_program_pathways.sql`，在默认的新加坡国际本硕升学计划卡片中补充高中毕业生的两条升学路径。迁移只匹配默认简介，已自行维护的项目卡片可在官网内容管理中核对并补充。官网展示与客服目录共用此内容。

确认初中升学及专升本路径可以对外介绍后，应用 `pending/031_singapore_junior_and_diploma_pathways.sql`，在 024 之后补充默认已发布卡片中的初中与大专升学路径。031 只匹配 024 生成的原文；已编辑或下架的卡片不会被改写，重复执行不会追加重复内容。已自行维护的卡片可在官网内容管理中使用「初中毕业生：路径介绍」等独立行，或用「初中毕业生可了解以下路径：」作标题并在后面逐行填写项目路径。文案只介绍路线，当期开班、招生和申请资格需另行核对。

## 班主任完整业务线

025后、启动新版前应用一次`pending/026_teacher_business.sql`。新增教学课程、班级开课、转班历史、整班考务发布去重及请假附件表；为既有成绩和考务增加教学阶段，默认unspecified，不推测历史阶段。课程没有金额字段。补齐班主任学务权限、管理员教学配置权限、管理员与主管投诉纠错权限；顾问申请进度改为只读。MySQL DDL会隐式提交，执行前按环境备份，部分执行时核对已有列再续跑，不重复执行ALTER。记录本次本机应用结果于logs/teacher-business-migration.json，云端尚未执行。完整职责及验收见docs/班主任业务线实施与验收-2026-11-16.md。

## 学生首页、草稿确认与生活知识

026 后依次应用一次 `pending/027_student_assistant_workspace.sql` 和 `pending/028_student_guidance_knowledge.sql`。027 新增助手办理草稿及公开生活资料的来源字段；028 新增指南详情和对话展示字段。既有会话、班级、教学课程、成绩、考务、请假附件和客户记录均保留。MySQL DDL 隐式提交，部分执行后先核对实际列，不能直接重复 ALTER。

迁移后，使用同一数据库配置执行 `python -m scripts.import_student_life_catalog --database 实际库名`，再按 `docs/student-workspace/README.md` 配对工作流和服务端配置。启动应用不会自动建表或迁移。回退仅恢复配套代码、Dify 画布及环境配置，新增表列可保留；不要删除历史业务数据。本轮已应用到本机环回的 education_service，其他环境需单独部署。
