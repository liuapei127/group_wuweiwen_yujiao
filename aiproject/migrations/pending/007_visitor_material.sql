-- 依赖 004 的 customer_source 与 006 的 visitor_account，均须采用 InnoDB。

CREATE TABLE visitor_material (
	source_id BIGINT UNSIGNED NOT NULL,
	visitor_id BIGINT NOT NULL,
	file_content MEDIUMBLOB,
	PRIMARY KEY (source_id),
	FOREIGN KEY(source_id) REFERENCES customer_source (id),
	FOREIGN KEY(visitor_id) REFERENCES visitor_account (id)
)ENGINE=InnoDB CHARSET=utf8mb4;
CREATE INDEX ix_visitor_material_visitor_id ON visitor_material (visitor_id);
