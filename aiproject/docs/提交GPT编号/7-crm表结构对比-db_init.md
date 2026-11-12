# 7 · `crm_lead` / `crm_follow_up` 与标准 `db_init.sql` 对比

**标准来源**：`教育服务_0914/2222通过表可以实现curd/db_init.sql`  
**本地 E2E 建表**：`CREATE TABLE IF NOT EXISTS`（无 DROP）

---

## 7.1 结论摘要

| 项 | 结论 |
| --- | --- |
| 字段主体 | 与标准 **基本一致**，可跑当前 consultant 代码 |
| 索引 | 本地 `crm_follow_up` **缺少** `idx_employee_id` |
| COMMENT | 本地建表无字段 COMMENT |
| 其余 29 表 | 本地测试库 **不存在** |
| `IF NOT EXISTS` | **不能**保证已与标准完全一致 |

---

## 7.2 `crm_lead` 差异

| 对比项 | db_init.sql | 本地 E2E |
| --- | --- | --- |
| 字段集合 | 含 `customer_profile_id` 等全部字段 | 已包含同名字段 |
| UNSIGNED | BIGINT UNSIGNED | BIGINT UNSIGNED |
| ENUM status | new/contacting/qualified/signed/lost | 同 |
| 索引 | idx_status, idx_owner, idx_customer_profile | 缺 idx_customer_profile（若本地简版未建） |
| 字符集 | utf8mb4_unicode_ci | utf8mb4 |

---

## 7.3 `crm_follow_up` 差异

| 对比项 | db_init.sql | 本地 E2E |
| --- | --- | --- |
| 字段 | 一致 | 一致 |
| 索引 | idx_lead_id, **idx_employee_id** | 仅 idx_lead_id |

---

## 7.4 建议（不自动执行）

1. 在**独立测试库**导入经审查的标准结构（去掉 DROP 段）。  
2. 合并上云前由集成负责人统一 schema 来源。  
3. `owner_employee_id=1` 仅为测试数据，**非**业务默认；与 `sys_user` 外键关系云端再核。
