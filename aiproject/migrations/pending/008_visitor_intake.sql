-- 依赖 004 的 customer_source 和 006 的 visitor_account。

CREATE TABLE visitor_intake (
	visitor_id BIGINT NOT NULL,
	advisor_id BIGINT NOT NULL,
	claimed_at DATETIME NOT NULL,
	last_contact_at DATETIME,
	manual_source_id BIGINT UNSIGNED,
	PRIMARY KEY (visitor_id),
	FOREIGN KEY(visitor_id) REFERENCES visitor_account (id),
	UNIQUE (manual_source_id),
	FOREIGN KEY(manual_source_id) REFERENCES customer_source (id)
)ENGINE=InnoDB CHARSET=utf8mb4;
CREATE INDEX ix_visitor_intake_advisor_id ON visitor_intake (advisor_id);

CREATE TABLE visitor_call (
	id BIGINT NOT NULL AUTO_INCREMENT,
	visitor_id BIGINT NOT NULL,
	advisor_id BIGINT NOT NULL,
	request_id VARCHAR(36) NOT NULL,
	notes TEXT NOT NULL,
	recorded_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uq_visitor_call_request UNIQUE (visitor_id, request_id),
	FOREIGN KEY(visitor_id) REFERENCES visitor_intake (visitor_id)
)ENGINE=InnoDB CHARSET=utf8mb4;
