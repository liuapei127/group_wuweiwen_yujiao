-- PF 客户资料与初筛结果。目标库若已有同名表，部署前须核对现有结构。

CREATE TABLE customer_source (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	source_type ENUM('text','pdf_resume','excel','import','manual') NOT NULL COMMENT '资料来源类型',
	raw_content TEXT COMMENT '原始文本内容',
	file_url VARCHAR(512) COMMENT '文件存储地址',
	file_name VARCHAR(255) COMMENT '原始文件名',
	parse_status ENUM('pending','success','failed') NOT NULL COMMENT '解析状态',
	parse_result JSON COMMENT '解析结果JSON',
	parse_error TEXT COMMENT '解析失败原因',
	operator_id BIGINT COMMENT '操作人用户ID',
	create_time DATETIME NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE INDEX idx_parse_status ON customer_source (parse_status);
CREATE INDEX idx_source_type ON customer_source (source_type);

CREATE TABLE customer_profile (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	customer_name VARCHAR(64) COMMENT '客户姓名',
	contact_info VARCHAR(128) COMMENT '联系方式',
	source_id BIGINT UNSIGNED COMMENT '来源资料ID',
	background_info JSON COMMENT '背景信息JSON',
	match_result ENUM('matched','partial','not_matched') COMMENT '匹配结论',
	matched_product VARCHAR(128) COMMENT '匹配产品线',
	match_score NUMERIC(5, 2) COMMENT '匹配得分',
	match_reason TEXT COMMENT '匹配理由',
	recommended_programs JSON COMMENT '推荐专业/项目列表',
	evaluator_id BIGINT COMMENT '研判人ID',
	create_time DATETIME NOT NULL COMMENT '创建时间' DEFAULT CURRENT_TIMESTAMP,
	update_time DATETIME NOT NULL COMMENT '更新时间' DEFAULT CURRENT_TIMESTAMP,
	PRIMARY KEY (id),
	FOREIGN KEY(source_id) REFERENCES customer_source (id)
);
CREATE INDEX idx_match_result ON customer_profile (match_result);
CREATE INDEX idx_matched_product ON customer_profile (matched_product);
CREATE INDEX idx_source_id ON customer_profile (source_id);
