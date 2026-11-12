# ENT 增量迁移

001_ent_reliability：成绩考试/提交标识、版本、更正历史；来源待办唯一约束、分配修订号和通知去重标识。

从 aiproject 运行 python -m scripts.migrate_ent_reliability --apply。当前脚本仅允许本机数据库。MySQL DDL 隐式提交，不能承诺失败后一键事务回滚；脚本先检查来源待办重复数据，逐列/逐索引检查，可在排除错误后重新运行。迁移不删除或合并既有数据。

001_ent_reliability_expected.sql 是迁移后的表结构校验基准，不应作为覆盖已有表的部署脚本。local_ent_validation 在历史表存在时叠加此基准，当前预期共32表。

首次本地执行前的行级备份在 logs/ent-migration-001-before.json（git忽略）；原有行及原有列内容已核对保留。云端尚未执行；云端执行前需按该环境备份、确认版本并演练。

旧成绩同一学生、课程、学期只有一条时回填默认考试标识；若有多条则保留每条并使用 legacy:<原ID>，不自动判断哪条是重考或重复。历史表写入 baseline，之前的修改记录未知，不虚构。
