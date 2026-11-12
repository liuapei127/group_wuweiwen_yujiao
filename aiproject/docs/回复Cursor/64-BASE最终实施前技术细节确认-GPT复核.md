# 64 BASE 最终实施前技术细节确认（GPT 复核）

日期：2026-11-12  
只确认四项实施细节。不覆盖此前的 64 号文件，也不改业务代码、数据库、生产配置和 Dify 工作流。未写明的架构仍以最终补充修订版为准。

## 1. 会话关联表的外键类型

2026-11-12 只读核对了本地 `education_service`，没有执行 DDL。

`ent_auth_session.id` 的实际定义是：`varchar(36)`，字符集 `utf8mb4`，排序规则 `utf8mb4_unicode_ci`，`NOT NULL`，主键。表引擎是 InnoDB，表排序规则同样是 `utf8mb4_unicode_ci`。现有二级索引只有 `user_id`。

`auth_service_session` 当前不存在，不能把它的字段类型说成已经建好。关联表 `auth_user_session_kid`、`auth_service_session_kid` 也还不存在。

因此：

- `auth_user_session_kid.session_id` 使用与现表完全相同的 `VARCHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL`。这样可以直接外键到 `ent_auth_session.id`，不必改现有会话主键。
- 创建 `auth_service_session` 时，`id` 必须使用同一类型、字符集、排序规则和 InnoDB。然后 `auth_service_session_kid.session_id` 才能直接外键过去。如果新建表用了 `CHAR(36)`、`ascii` 或其他排序规则，先改这张新表，不改 `ent_auth_session.id`。

两张关联表的主键 `(session_id, kid)` 已经能按会话查找。泄露处置要按 `kid` 找出全部会话，所以每张表再加普通索引 `INDEX idx_kid (kid)`。不要只靠主键完成这一种查询。

## 2. 委托操作名单

换票仍不注册、不开放。数据关系确定为：

- `auth_token_exchange_policy` 有独立 `policy_id`。
- `auth_token_exchange_policy_operation` 以 `(policy_id, operation_code)` 为主键，保存当前允许的操作编码。
- 委托会话在 `ent_auth_session.policy_id` 保存这份政策。该列可空，普通登录会话为 NULL。
- 目标模块每次请求读取：会话未撤销、父会话仍有效、政策仍启用，且会话里的 `policy_version` 等于政策当前版本。通过后再读取该版本的操作行，与用户数据库权限取交集。名单不缓存进令牌。
- 政策停用、版本变化或操作名单变化后，旧委托会话直接拒绝。不沿用旧名单，也不自动获得新增操作。需要按第 5 节重新换票。
- 委托会话的 `parent_session_id` 非空。这种会话不能再作为换票的源会话，因此不能嵌套，也不能二次换票。
- 委托会话不签发 Refresh Token。它的 `exp` 不得晚于父会话的绝对结束时间，也不能晚于父会话当前 `exp`。委托不能把父会话延长。

服务令牌进入换票接口时，受众仍必须是 `edu-auth:token-exchange`。

## 3. 刷新令牌的浏览器保存与空闲更新

Access Token 放在内存中，通过 `Authorization: Bearer` 发送。不写入 Cookie，也不写入 `localStorage`。

Refresh Token 只放在名为 `__Secure-` 前缀的 Cookie 中：`Secure`、`HttpOnly`、`SameSite=Strict`，`Path=/api/v1/auth`。脚本读不到这张 Cookie，浏览器也不会在跨站请求里附带它。

CSRF Cookie 使用 `__Host-` 前缀，具体属性见第 6 节。刷新和登出只接受 POST。除 Cookie 外，还要同时满足：请求头 `Origin` 等于配置的门户来源；CSRF Cookie 与请求头 `X-CSRF-Token` 一致。缺 `Origin`、来源不对或两个 CSRF 值不一致，都拒绝。GET 不执行刷新或登出。Bearer 访问本身不依赖 Cookie，不额外做这组 CSRF 检查。

正式环境使用 HTTPS，Cookie 必须带 `Secure`。本机 `127.0.0.1` 或 `localhost` 在当前 Chromium 中属于可信来源，可以带 `Secure`。只有主机确实是环回地址且浏览器拒绝该 Cookie 时，才允许本地配置关闭 `Secure`。非环回主机一律不能关闭。Safari 使用 `SameSite=Strict`；不使用 `SameSite=None`。门户不放在跨站 iframe 里，否则 Strict Cookie 不会送出。

`last_used_at` 不在每次业务请求时更新。采用条件更新：只有原值早于当前时间 5 分钟以上才写入。持续使用时，每个会话大约 5 分钟写一次。因为未记录的活动只会比 `last_used_at` 更晚，空闲判断只会提前，不会延后；相对 2 小时空闲超时，最大误差是提前 5 分钟。更新失败时保留旧时间，超时只会更早发生。

## 4. 组织关系的一致性和历史

授权查询除了成员状态和时间窗口，还要确认用户当前 `user_type` 仍是 `employee` 或 `admin`。学生即使留下旧行，也不获得组织范围。

仅有查询还不够。`sys_user` 的更新触发器在账号类离开员工或管理员时，把该用户仍有效的 `sys_org_member` 改为停用；成员表的更新触发器发现该行被停用，或它不再被当作有效关系时，删除 `sys_user_primary_org` 中指向它的指针。插入和更新成员时，原有触发器继续拒绝学生。这样，先有组织关系、后来改成学生的账号，不会继续带着主部门指针。

现有 `ent_auth_audit` 已核对：`details` 是 `text`，可以附带一段 JSON，但没有组织、起止时间和变更前后的列，并且与登录审计混在同一张表。它不作为组织关系史的存储。

组织历史使用独立的 `sys_org_member_history`，保存用户、组织、变更前后的状态和起止时间、主部门指针是否被清除，以及操作者。重新加入同一组织时，先把当前行的上一段写入这张历史表，再更新原成员行。同时在 `ent_auth_audit` 记一条动作和历史行编号，方便按人检索，但不靠它还原关系。

成员关系停用时，同一事务删除指向该成员行的主部门指针。指针删除与历史插入要么一起提交，要么一起回滚。须写入历史的范围和到期清理见第 7 节。

## 5. 委托政策版本

`auth_token_exchange_policy` 增加 `policy_version`，从 1 起计。委托会话在签发时写入当时的 `policy_id` 和 `policy_version`。

策略的任何修改都先把版本加 1，再写入新的操作名单。修改包括停用、重新启用、增加操作和删除操作。旧版本委托会话在下一次请求时因为版本不一致被拒绝，不能继续使用，也不能自动获得新版本里多出来的操作。用户若仍需要委托，必须重新换票，从而拿到新版本。

换票接口仍不注册、不开放。

## 6. Cookie 名称和属性

| Cookie | 名称约束 | 属性 |
| --- | --- | --- |
| CSRF | 使用 `__Host-` 前缀 | `Secure`，`Path=/`，不设置 `Domain`，`SameSite=Strict`。不设置 `HttpOnly`，以便门户脚本读出并放入 `X-CSRF-Token` |
| Refresh | 使用 `__Secure-` 前缀 | `Secure`，`HttpOnly`，`SameSite=Strict`，`Path=/api/v1/auth`。不设置 `Domain` |

`Origin` 与 `X-CSRF-Token` 的双重核对保持不变。`__Host-` 前缀本身要求 `Secure`、`Path=/` 且不能有 `Domain`，实施时不得放宽这三项。环回地址上若浏览器拒绝 `Secure` Cookie，只允许在该环回主机的本地配置中关闭 `Secure`；此时不能使用 `__Host-` 前缀，本地改用无此前缀的 CSRF Cookie 名称，非环回环境禁止这种例外。

## 7. 组织历史的覆盖范围和到期清理

以下变化都写入 `sys_org_member_history`，并记录变化前后的状态、起止时间，以及主部门指针是否被清除：

- 员工或管理员账号类改为学生，触发器因此停用组织关系。
- 员工账号停用，并因此停用其组织关系。
- 成员关系被停用。
- 主部门指针被清除。
- 触发器自动完成的上述修改。

人工通过接口直接修改组织关系时，操作者记录为该员工。触发器连带停用关系、清理任务删除过期指针，以及其他没有当前操作者的自动修改，操作者记录为 `system`。管理员停用账号或修改账号类时，账号动作仍可记入 `ent_auth_audit`；由此触发的组织历史行记为 `system`。

`effective_to` 到期不会触发 MySQL 触发器。增加一个清理任务：找出 `effective_to` 已到、且仍被 `sys_user_primary_org` 指向的成员行，删除这些指针，并写入一条操作者为 `system` 的历史。清理可以延迟，授权不能延迟。授权查询每次都判断 `effective_from` 已到、`effective_to` 为空或未到、成员状态有效、账号类仍是员工或管理员。清理任务尚未运行时，过期关系也不授权。

本轮没有修改业务代码、数据库、生产配置和已发布工作流。此前所有 64 号文件都保留。BASE 总体架构不再改写。正式编码按已定阶段进行：每个阶段先有安全基线、备份和回滚方案，阶段完成并提交、测试、验收之后，才进入下一阶段。8000 在安全验收清单全部通过前保持 `blocked`。
