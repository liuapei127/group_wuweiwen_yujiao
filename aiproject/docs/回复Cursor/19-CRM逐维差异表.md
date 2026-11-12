# 19 · CRM 两表逐维核对（人工 + 14 号 JSON）

标准来源：`教育服务_0914/2222通过表可以实现curd/db_init.sql`（字节 SHA256 见 `18-CRM差异判定.md` 或重算）  
数据库：`education_service` 本机实例  
**结论范围**：31 表仅 **存在性**；下表仅 **crm_lead / crm_follow_up**

## 判定摘要

| 表 | 列集合 | 类型/枚举 | 索引 | 外键 | 字符集 |
| --- | --- | --- | --- | --- | --- |
| crm_lead | 与标准一致（18 字段） | 与 `SHOW CREATE` 一致 | idx_status, idx_owner, idx_customer_profile | 双方均无显式 FK | utf8mb4_unicode_ci |
| crm_follow_up | 7 字段一致 | follow_type 枚举一致 | idx_lead_id, idx_employee_id | 无显式 FK | utf8mb4_unicode_ci |

**不能宣称**：「自动 diff_count=0」或「31 表结构完全一致」。  
**可宣称**：在 **抽查维度** 下，两表与标准 `db_init` **未发现差异**（2026-11-11 本库）。

## crm_lead（代表性字段）

| 列 | 标准要点 | 库中实际 | 结论 |
| --- | --- | --- | --- |
| id | BIGINT UNSIGNED PK AI | 同 | 一致 |
| status | ENUM(new,contacting,...) | 同 | 一致 |
| owner_employee_id | BIGINT UNSIGNED NOT NULL | 同 | 一致 |
| customer_profile_id | BIGINT UNSIGNED NULL | 同 | 一致 |

（其余字段见 `14-CRM结构完整对比.json` → columns_db，逐项 TYPE/NULL/DEFAULT 与标准 SHOW CREATE 肉眼一致。）

## crm_follow_up

| 列 | 标准要点 | 库中实际 | 结论 |
| --- | --- | --- | --- |
| lead_id / employee_id | UNSIGNED NOT NULL | 同 | 一致 |
| follow_type | ENUM(phone,wechat,...) | 同 | 一致 |
| content | TEXT NOT NULL | 同 | 一致 |

## 外键

标准 SQL 与当前库 **均无 CONSTRAINT FOREIGN KEY**；业务关联靠应用层 lead_id。

## 与 08 号评审对齐

- 否定旧脚本「列名子串匹配 ⇒ 无差异」。  
- 本表为 **人工逐维核对结论**；若标准或库变更，须重跑 `compare_schema_crm_full.py` 并更新本表。
