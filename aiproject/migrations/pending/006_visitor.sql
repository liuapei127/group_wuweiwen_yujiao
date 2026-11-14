-- 官网游客账号与会话。

CREATE TABLE visitor_account (
	id BIGINT NOT NULL AUTO_INCREMENT,
	username VARCHAR(64) NOT NULL,
	name VARCHAR(64) NOT NULL,
	contact VARCHAR(128) NOT NULL,
	password_hash VARCHAR(255) NOT NULL,
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	UNIQUE (username)
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE TABLE visitor_session (
	digest VARCHAR(64) NOT NULL,
	visitor_id BIGINT NOT NULL,
	expires_at DATETIME NOT NULL,
	PRIMARY KEY (digest),
	FOREIGN KEY(visitor_id) REFERENCES visitor_account (id)
)ENGINE=InnoDB CHARSET=utf8mb4;
CREATE INDEX ix_visitor_session_expires_at ON visitor_session (expires_at);
CREATE INDEX ix_visitor_session_visitor_id ON visitor_session (visitor_id);
