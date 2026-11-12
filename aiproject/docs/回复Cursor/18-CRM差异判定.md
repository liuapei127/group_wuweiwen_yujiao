# CRM 差异判定（第三轮）

- 标准 SQL SHA256（文件字节）：`0ad61254ef3277d4e392a03de738991411363dc4a9244bc510025691ad4e8c31`
- 库表数量：31（结论范围：清单存在性 + CRM 下列维度）

## 判定摘要

### `crm_lead`
- 库列数：18；索引行：4
- 标准 SQL 中实际外键：无（与 db_init 一致为**无显式 FK**）；SHOW CREATE 含 FK：False
- 列名均在标准 SQL 片段内

### `crm_follow_up`
- 库列数：7；索引行：3
- 标准 SQL 中实际外键：无（与 db_init 一致为**无显式 FK**）；SHOW CREATE 含 FK：False
- 列名均在标准 SQL 片段内

完整 JSON：
```json
{
  "summary": {
    "standard_sql_path": "D:\\Project course\\group_wuweiwen_yujiao\\教育服务_0914\\2222通过表可以实现curd\\db_init.sql",
    "standard_sql_sha256": "0ad61254ef3277d4e392a03de738991411363dc4a9244bc510025691ad4e8c31",
    "database": "education_service",
    "table_count": 31,
    "crm_tables": {
      "crm_lead": {
        "column_count_db": 18,
        "index_count": 4,
        "foreign_keys_in_ddl": false,
        "diffs": [],
        "match_note": "列名均在标准 SQL 片段内"
      },
      "crm_follow_up": {
        "column_count_db": 7,
        "index_count": 3,
        "foreign_keys_in_ddl": false,
        "diffs": [],
        "match_note": "列名均在标准 SQL 片段内"
      }
    }
  },
  "diffs": []
}
```