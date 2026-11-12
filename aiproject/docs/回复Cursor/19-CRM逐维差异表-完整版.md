# 19 · CRM 逐维差异表（完整版，自 14 号生成）

- 标准 SQL：`D:\Project course\group_wuweiwen_yujiao\教育服务_0914\2222通过表可以实现curd\db_init.sql`
- 库：`education_service` · table_count 见 14
- **结论**：下列字段/索引与标准 `db_init.sql` **一致**（本机核对日 2026-11-11）
- **外键**：标准与库均无显式 CONSTRAINT FK；关联靠 `lead_id` 等应用字段

## `crm_lead`

| 列 | TYPE | NULL | DEFAULT | EXTRA | 结论 |
| --- | --- | --- | --- | --- | --- |
| `id` | `bigint unsigned` | NO | None | auto_increment | 与 db_init 一致 |
| `customer_name` | `varchar(64)` | NO | None | — | 与 db_init 一致 |
| `contact_info` | `varchar(128)` | YES | None | — | 与 db_init 一致 |
| `gender` | `enum('M','F','U')` | YES | U | — | 与 db_init 一致 |
| `age` | `int` | YES | None | — | 与 db_init 一致 |
| `education_level` | `varchar(64)` | YES | None | — | 与 db_init 一致 |
| `intended_country` | `varchar(128)` | YES | None | — | 与 db_init 一致 |
| `intended_major` | `varchar(128)` | YES | None | — | 与 db_init 一致 |
| `background_info` | `text` | YES | None | — | 与 db_init 一致 |
| `customer_profile_id` | `bigint unsigned` | YES | None | — | 与 db_init 一致 |
| `source_channel` | `varchar(64)` | YES | None | — | 与 db_init 一致 |
| `status` | `enum('new','contacting','qualified','signed','lost')` | NO | new | — | 与 db_init 一致 |
| `owner_employee_id` | `bigint unsigned` | NO | None | — | 与 db_init 一致 |
| `last_contact_time` | `datetime` | YES | None | — | 与 db_init 一致 |
| `lost_reason` | `varchar(255)` | YES | None | — | 与 db_init 一致 |
| `remark` | `text` | YES | None | — | 与 db_init 一致 |
| `create_time` | `datetime` | NO | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 与 db_init 一致 |
| `update_time` | `datetime` | NO | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP | 与 db_init 一致 |

| Key | 唯一 | 列序 | 列名 |
| --- | --- | --- | --- |
| PRIMARY | 是 | 1 | id |
| idx_status | 否 | 1 | status |
| idx_owner | 否 | 1 | owner_employee_id |
| idx_customer_profile | 否 | 1 | customer_profile_id |

表字符集/排序：utf8mb4 / utf8mb4_unicode_ci（见 SHOW CREATE in 14）

## `crm_follow_up`

| 列 | TYPE | NULL | DEFAULT | EXTRA | 结论 |
| --- | --- | --- | --- | --- | --- |
| `id` | `bigint unsigned` | NO | None | auto_increment | 与 db_init 一致 |
| `lead_id` | `bigint unsigned` | NO | None | — | 与 db_init 一致 |
| `employee_id` | `bigint unsigned` | NO | None | — | 与 db_init 一致 |
| `follow_type` | `enum('phone','wechat','meeting','email','other')` | YES | None | — | 与 db_init 一致 |
| `content` | `text` | NO | None | — | 与 db_init 一致 |
| `next_plan` | `varchar(255)` | YES | None | — | 与 db_init 一致 |
| `create_time` | `datetime` | NO | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 与 db_init 一致 |

| Key | 唯一 | 列序 | 列名 |
| --- | --- | --- | --- |
| PRIMARY | 是 | 1 | id |
| idx_lead_id | 否 | 1 | lead_id |
| idx_employee_id | 否 | 1 | employee_id |

表字符集/排序：utf8mb4 / utf8mb4_unicode_ci（见 SHOW CREATE in 14）
