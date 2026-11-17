-- 兼容已创建旧版暂存表的环境。032 已在新建表时包含该列。
SET @cs_portrait_ddl = IF(
    EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = DATABASE() AND table_name = 'cs_visitor_profile' AND column_name = 'attributes'
    ),
    'SELECT 1',
    'ALTER TABLE cs_visitor_profile ADD COLUMN attributes JSON NULL COMMENT ''待并入客户画像的规则属性'''
);
PREPARE cs_portrait_migration FROM @cs_portrait_ddl;
EXECUTE cs_portrait_migration;
DEALLOCATE PREPARE cs_portrait_migration;
