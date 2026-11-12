# 64 BASE 统一身份认证架构（GPT 最终补充修订版）

日期：2026-11-12  
本文件只补充密钥关联、委托会话、刷新令牌生命周期和组织表兼容性。不覆盖前面三份 64 号文件，也不重写已认可的整体架构。未在这里改写的内容，仍以 `64-BASE统一身份认证架构深化与分阶段开发计划-GPT最终复核版.md` 为准。  
本轮只做设计，不改业务代码、数据库、认证逻辑、生产配置和 Dify 工作流，也不执行 DDL。

有一处取代最终复核版的对应段落：用户会话和服务会话都不再用单独一个 `signing_kid` 列作为密钥关联的依据。其余 RS256、受众、8000 验收清单和回滚方式不变。

## 1. 会话与密钥的多对多关系

一个 `sid` 会跨过密钥轮换。K1 签发的 access 尚未过期时，同一次刷新已经改由 K2 签发下一张 access。只在 `ent_auth_session` 上保存一个 `signing_kid`，会丢掉 K1 与这个会话的关系，密钥泄露时撤不干净。

比较：

| 方案 | 能表达的事实 | 维护成本 | 判断 |
| --- | --- | --- | --- |
| `auth_token_issuance`：每张 access 一行，含 `jti`、`sid`、`kid`、过期和撤销 | 可以单独作废一张 access | 每次签发都增加一行，每个请求还要再查这张表，否则单张撤销没有意义 | 当前泄露处理要求的是整个 `sid` 失效，不需要先做到单张 access 撤销 |
| 会话与 `kid` 的关联表 | 记录这个会话用过的每一把密钥。任一把泄露就撤销整个会话 | 只在首次使用某把密钥时插入一行；请求路径仍只查会话是否撤销 | **采用** |

用户会话和服务会话分开建表，避免一个 `session_id` 同时去关联两种会话：

```sql
CREATE TABLE auth_user_session_kid (
  session_id VARCHAR(36) NOT NULL,
  kid VARCHAR(64) NOT NULL,
  first_issued_at DATETIME NOT NULL,
  PRIMARY KEY (session_id, kid),
  CONSTRAINT fk_user_session_kid FOREIGN KEY (session_id) REFERENCES ent_auth_session (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE auth_service_session_kid (
  session_id VARCHAR(36) NOT NULL,
  kid VARCHAR(64) NOT NULL,
  first_issued_at DATETIME NOT NULL,
  PRIMARY KEY (session_id, kid),
  CONSTRAINT fk_service_session_kid FOREIGN KEY (session_id) REFERENCES auth_service_session (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
```

`ent_auth_session` 不增加 `signing_kid`。历史门户会话没有关联行，仍然只由 8002 的 HS256 验签器接受。BASE 签发或刷新 access 时，在同一事务里写入会话，并插入当前 `kid`；主键重复说明这把密钥已经记录过，保持原 `first_issued_at`。

K1 被标为泄露时：查出两张关联表里 `kid=K1` 的全部 `session_id`，撤销这些用户会话、服务会话以及它们的刷新家族。同一 `sid` 下由 K2 签发、尚未过期的 access 也一起失效。只用过 K2 的其他会话不受影响。服务会话使用同一规则，不把服务客户端写成员工。

请求验证仍然是验签加上会话未撤销。关联表不放在普通请求的必查路径上，只在签发和泄露处置时写入或读取。

## 2. Token Exchange 的会话契约

仍然不注册接口，也不开放换票。下面是将来启用单条政策时必须遵守的会话约定。

调用换票的服务令牌，受众必须是 `edu-auth:token-exchange`，并且 `token_use=service_access`。只验证签名、或拿着业务受众的服务令牌，都不能调用换票。该服务还必须出现在这一条政策里。

新的 `sid` 仍是一行 `ent_auth_session`。被代表的人是原来的用户，所以目标模块继续按用户会话查找，不查服务会话表。为了不破坏现有插入，新增列全部可空：

| 列 | 普通登录会话 | 委托会话 |
| --- | --- | --- |
| `parent_session_id` | NULL | 被换票的那张用户会话 |
| `delegate_client_id` | NULL | 发起换票的服务客户端 |
| `audience` | 该用户 access 的资源受众 | 政策里的目标受众 |

目标模块用令牌里的 `sid` 读取 `ent_auth_session`，并确认行上的 `audience` 与令牌受众一致、会话未撤销、用户仍有效。权限仍从数据库读取。

原始会话撤销、过期或停用时，以它为 `parent_session_id` 的委托会话在同一次操作中一并撤销。之后每次使用委托令牌，还要再确认父会话仍然有效；父会话已经失效则拒绝。这样不依赖只跑一次的级联更新。

委托会话的主体仍是用户，不是服务。服务客户端不能在目标模块行使该用户的全部权限。政策里必须写出允许的操作名单；目标模块把数据库中的用户权限与这份名单取交集。名单为空则拒绝换票。服务身份只记在 `delegate_client_id` 和审计里，不变成员工主体。

学生 access 不能换成员工受众。服务令牌自己也不能被换成用户 access。

## 3. Refresh Token 生命周期

刷新串仍是 256 位随机值，只存 SHA-256，沿用 `family_id`、行锁、轮换和重放撤销。生命周期补齐如下。

| 规则 | 默认值 | 可否按环境配置 | 安全上限 |
| --- | --- | --- | --- |
| Access 有效期 | 60 分钟 | 可以缩短 | 不得超过 60 分钟 |
| 单张刷新串有效期 | 12 小时 | 可以 | 不得超过 14 天 |
| 会话绝对寿命 | 12 小时，从会话创建起算 | 可以 | 不得超过 7 天 |
| 空闲超时 | 2 小时 | 可以 | 不得超过 12 小时 |
| 过期或撤销后的保留 | 7 天 | 否 | 7 天，供重放判断 |

轮换时，新刷新串的 `expires_at` 取「现在加上单张刷新串有效期」和「会话创建时间加上绝对寿命」中较早的那个。轮换不能把会话延长到绝对寿命之后。

空闲从会话的 `last_used_at` 计算。成功的业务验签和成功的刷新都更新它。超过空闲时间后，整族刷新串和会话撤销。

账号停用和修改密码立即撤销该用户的全部会话、委托会话和刷新族。登出撤销当前这一个会话、它的委托会话和刷新族。

Access 已经过期时，登出不再接受这张过期 JWT。客户端改把尚未过期的刷新串交给登出接口；服务端按哈希找到家族并撤销。两张凭证都缺失或都已过期时，不创建新会话，按已登出结束。

清理任务只删除「已经过期或撤销，并且超过 7 天保留期」的刷新行和会话行。保留期内，旧刷新串仍能触发整族撤销。超过保留期后，未知哈希只返回 401。清理按家族进行，不能先删掉仍被引用的重放标记。

启用刷新前仍须通过 N14 和 N15。上述时间不改变 8000 的开放清单。

## 4. 组织表与当前库的兼容性

2026-11-12 对本地 `education_service` 做了只读核对，版本仍是 MySQL 8.0.27。没有执行 DDL。

| 检查 | 结果 |
| --- | --- |
| `sys_user.id` | `bigint unsigned`，主键，自增 |
| `sys_organization.id` | `bigint unsigned`，主键，自增 |
| `sys_role.id` | `bigint unsigned`，主键 |
| `parent_id`、`manager_id`、`role_id` | 都是 `bigint unsigned`，类型与对应主键一致 |
| 现有约束 | 两张表都没有外键。用户表另有 `uk_username`；组织表有 `parent_id`、`manager_id` 普通索引 |
| 引擎和排序规则 | `sys_user`、`sys_role`、`sys_organization` 都是 InnoDB、`utf8mb4_unicode_ci` |
| 行数 | 用户 14 行：员工正常 5、员工停用 3、学生正常 4、学生停用 1、管理员正常 1。组织 4 行 |
| 脏引用 | `parent_id`、`manager_id`、`role_id` 的悬空引用都是 0。没有学生被写成组织负责人 |

因此最终复核版里的两张新表，列类型可以写成 `bigint unsigned`，外键在类型、引擎和排序规则上与现表兼容。开发时仍要先重复一次悬空检查；本次没有脏引用，不代表以后写入前可以跳过。

5 名学生的 `department` 都有字符串。这只是现有显示字段，不是组织成员。迁移时不得把这些字符串插入 `sys_org_member`。

同一员工重新加入同一组织时，不插入第二行。`UNIQUE(user_id, org_id)` 只保留当前关系；重新加入改为更新这一行的状态、`effective_from` 和 `effective_to`，并把上一段起止时间写入审计。历史不靠第二条成员行保存。

学生不能建立员工组织关系。外键本身看不出 `user_type`，所以 `sys_org_member` 增加 `BEFORE INSERT` 和 `BEFORE UPDATE` 触发器：账号类不是 `employee` 或 `admin` 时，以 SQLSTATE 拒绝。这是数据库规则，不只是应用判断。

并发测试使用两个独立连接。锁定顺序固定为：先锁 `sys_user`，再按 `sys_org_member.id` 升序锁成员行，最后锁 `sys_user_primary_org`。遇到主键或唯一键冲突（错误 1062）时回滚，重新读取后再决定插入或更新。遇到死锁（错误 1213）时整笔回滚，最多重试 3 次，并加入短暂随机等待。重试耗尽就向调用方返回冲突，不留下半个主部门指针。

## 5. BASE-01～05 仍待验收

有相关实现或材料，不等于这些原始任务卡已经验收。

| 卡 | 本次状态 | 还缺的证据 |
| --- | --- | --- |
| BASE-01 | 待验收 | 本地健康检查有过记录。腾讯云上的工程入口还没有本次启动证据 |
| BASE-02 | 待验收 | 仓库清单、分支规范和一次不含密钥的提交尚未完成。仍禁止未审查就 `git add` 整棵目录 |
| BASE-03 | 待验收 | 31 张表脚本和本机库存在，不能代替按该卡记录的一次创建、读取、更新和删除 |
| BASE-04 | 待验收 | `.env` 里有密钥变量，还没有应用命名清单和轮换记录 |
| BASE-05 | 待验收 | 还没有腾讯云 `aiproject` 的真实启动记录。本机 Compose 或本机 8000 不能代替 |

统一身份的设计进度不改变上表。

本轮没有修改业务代码、数据库、认证逻辑、生产配置和已发布工作流。前面三份 64 号文件都保留。
