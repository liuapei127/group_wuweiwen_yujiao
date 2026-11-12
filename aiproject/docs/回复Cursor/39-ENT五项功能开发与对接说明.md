# 39 ENT 五项功能开发与对接说明

日期：2026-11-11。阶段：本地后端第一版，未云端发布，未作为全链路验收。

## 做了哪些功能

| 需求 | 实现 | 仍需对接 |
| --- | --- | --- |
| ENT-06 组织查询 | 启用组织列表、关键词搜索；启用员工姓名和部门目录；单独授权查联系方式 | 团队维护真实组织和人员数据，Dify 接口调用；组织职能说明当前表无专用字段 |
| ENT-07 新人指引 | 按关键词/分类检索启用指南；授权编辑人员录入指南 | 把真实指南整理后录入；Dify 基于检索内容回答并标明指南标题，当前非向量 RAG |
| ENT-08 成绩 | 录入、按学生/学期查询、整条更正；验证学生存在且启用；记录录入人 | BASE 签发成绩读写权限和学生范围；STU 对齐学生 ID，确认成绩量表与重复考试规则 |
| ENT-10 投诉 | 本人被指派工单列表/详情；pending→processing→resolved→closed；解决和关闭必须有方案；条件更新防止覆盖新状态 | STU 提交并分配工单、展示或通知结果；ENT 不擅自把 is_notified 置 1 |
| ENT-13 待办 | 本人创建/查询/到期过滤/完成/取消；扫描明确指派的请假与投诉生成待办；到期生成站内通知；独立循环任务 | 运维启动扫描任务，前端或 Dify 查询站内通知；微信/短信/邮件未接；日报催交规则未定 |

本轮没有清库、没有执行迁移、没有连接真实 MySQL。模型对应标准 SQL 的既有六张表，组织/指南/成绩/投诉/待办/通知均不新建云端表。测试使用内存 SQLite 建表。

## 接口表

所有路径前缀为 /api/v1/enterprise，全部依赖 require_employee。

| 方法 | 后缀 | 用途 |
| --- | --- | --- |
| GET | /organizations | 组织列表；keyword、limit |
| GET | /organizations/colleagues | 按 name 搜索同事，只返回 ID、姓名、部门 |
| GET | /colleagues/{employee_id}/contact | directory:contacts 权限查询员工联系方式 |
| GET | /onboarding-guides | keyword、category、page、page_size 检索指引 |
| POST | /onboarding-guides | guides:write 权限录入 title、category、content |
| POST | /scores | scores:write 且学生在范围内，录入成绩 |
| GET | /scores | scores:read 且学生在范围内；student_id 必填，semester 可选 |
| PUT | /scores/{score_id} | 更正成绩，禁止更换所属学生 |
| GET | /tickets | 只看本人指派工单；status 可选 |
| GET | /tickets/{ticket_id} | 本人工单详情 |
| PATCH | /tickets/{ticket_id} | expected_status、status、solution；陈旧或非法流转返回 409 |
| POST | /todos | 本人待办 title、description、due_time、priority |
| GET | /todos | 本人列表；due_only=true 查询已到期的未完成待办 |
| PATCH | /todos/{todo_id} | expected_status、status；终态不可再变更 |
| GET | /notifications | 本人站内通知 |

成绩请求字段：student_id、course_name、score、semester（可选）、credit（可选）。当前分数边界是数据库 DECIMAL(5,2) 可容纳的非负数 0～999.99，不擅自假定所有考试满分 100；课程量表、及格规则需要产品确定。精度最多两位，学分最多一位。

当前分数更正不保留历史版本，重复提交也不会自动合并；若需要审批、历史审计、唯一考试编号或幂等重试，需按团队规则追加。学生端只读本人接口不在 ENT 本轮实现中。

## 身份与权限

EmployeePrincipal 新增 permissions 和 student_ids，默认都是空集合，保持原有 EmployeePrincipal(employee_id=...) 调用兼容。它们只能由以后可信认证后端填充，接口参数不能赋予自己权限。成绩即使有权限，也必须学生 ID 属于范围。普通员工默认无法录入或读取成绩、录入指南或读取同事联系方式。

生产认证仍默认 blocked/503，未增加任何环境变量放行路径。测试通过隔离应用覆盖身份验证业务权限，不表示 JWT 已完成。

## 定时待办如何运行

在已正确配置数据库与部署范围的环境中，从 aiproject 目录执行：

python -m scripts.run_ent_reminders --once

持续扫描：

python -m scripts.run_ent_reminders --interval 60

本轮没有替用户启动常驻进程。扫描是服务端任务，不能开放给普通 Dify 访客任意调用。

任务读取已明确分配审批人的 pending 请假，及已明确分配处理人的 pending/processing 投诉，生成 todo_item。单次每类最多处理 200 条未生成来源；下一轮继续扫描。读取已到期 pending/in_progress 待办，写 notification_log 的 system 通知。重复扫描不重复生成同一业务来源待办或同一待办通知。MySQL 路径使用行锁串行处理相同来源，但尚未做真实 MySQL 多工作进程并发验证。

notification_log 的 channel=system、status=sent 仅表示已写入本系统站内信箱，可以通过通知接口读取，绝不表示微信/短信/邮件发送成功。这里的主动是后台定时产生提醒，界面仍需轮询或后续接推送通道。

当前自动生成的业务待办不自动随源单据结案或转派同步；可由本人完成/取消。业务结案自动清理、转派同步、失败重试、延期后重复提醒以及日报催交，仍需下一轮补齐，不能据此宣称完整主动推送交付。

时间沿用现有业务 now_naive 约定；待办输入拒绝带时区时间，部署端需确保服务端时区与业务约定一致，后续应统一时区契约。

## 验证结果

Python 3.13 本地执行 python -m pytest tests -q：30 passed，退出码 0。保留上一轮 24 项回归，新增六项场景测试，涵盖目录过滤、指南权限和检索、成绩范围/精度/更正、投诉授权与状态、提醒去重和待办终态、默认认证拒绝。

完整输出及源码指纹见 38-ENT五项功能开发与测试.json。不是 MySQL、真实 JWT、云端、Dify 或学生通知验收。测试含一条 httpx 弃用提示。

## 接下来还需完成

1. BASE 确定并实现可信身份，以及成绩、人员信息和指南编辑权限。
2. STU 确定可信工单分配规则并联调投诉结果；客户端不能随意给自己分配员工。
3. 录入真实组织和新人指南资料；Dify 接通检索并用原文依据回答。
4. 运维启动扫描任务，接站内通知展示；选定外部通知通道后再开发投递。
5. MySQL 上做结构兼容、自动 ID、事务和并发验证，再进行云端与 Dify 端到端验收。

代码目录：app/modules/enterprise_support；扫描入口：scripts/run_ent_reminders.py；测试：tests/test_ent_support.py。路由已注册，/openapi.json 可见新增接口。
