-- Existing MySQL 8 installations. Safe to rerun without resetting administrator edits.
CREATE TABLE IF NOT EXISTS website_section (
    id BIGINT NOT NULL AUTO_INCREMENT,
    anchor VARCHAR(24) NULL,
    title VARCHAR(100) NOT NULL,
    sort_order INT NOT NULL,
    published BOOLEAN NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_website_section_anchor (anchor)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS website_section_card (
    id BIGINT NOT NULL AUTO_INCREMENT,
    section_id BIGINT NOT NULL,
    title VARCHAR(100) NOT NULL,
    content TEXT NOT NULL,
    sort_order INT NOT NULL,
    published BOOLEAN NOT NULL,
    PRIMARY KEY (id),
    KEY ix_website_section_card_section_id (section_id),
    FOREIGN KEY (section_id) REFERENCES website_section (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

START TRANSACTION;
INSERT INTO website_section (anchor, title, sort_order, published)
VALUES ('about', '关于粤教', 10, TRUE), ('programs', '留学项目', 20, TRUE)
ON DUPLICATE KEY UPDATE id = id;

INSERT INTO website_section_card (section_id, title, content, sort_order, published)
SELECT section.id, seed.title, seed.content, seed.sort_order, TRUE
FROM website_section AS section
JOIN (
    SELECT 'about' AS anchor, '留学与升学服务' AS title,
           '了解新加坡升学和德国职业培训项目。注册后可预约讲座、提交手头已有的材料，由顾问跟进。' AS content, 10 AS sort_order
    UNION ALL SELECT 'about', '数字化服务',
           '官网集中提供政策、课程和活动查询。顾问工作台汇总材料和跟进记录，方便顾问核对资料和补录。', 20
    UNION ALL SELECT 'programs', '新加坡国际本硕升学计划',
           '提供面向不同学历阶段的升学路径，以及酒店和航空方向的就业项目。', 10
    UNION ALL SELECT 'programs', '中德精英人才共建计划',
           '了解德国双元制职业培训和企业匹配流程，项目包含语言学习与岗位准备。', 20
) AS seed ON seed.anchor = section.anchor
WHERE section.id NOT IN (
    SELECT section_id FROM (SELECT DISTINCT section_id FROM website_section_card) AS initialized
);

INSERT INTO ent_auth_role_permission (role_id, permission)
SELECT id, 'website-content:manage' FROM sys_role WHERE role_code = 'admin'
ON DUPLICATE KEY UPDATE permission = 'website-content:manage';
COMMIT;
