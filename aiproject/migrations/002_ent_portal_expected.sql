CREATE TABLE ent_auth_role_permission (
	role_id BIGINT NOT NULL, 
	permission VARCHAR(96) NOT NULL, 
	PRIMARY KEY (role_id, permission)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE ent_auth_student_scope (
	user_id BIGINT NOT NULL, 
	student_id BIGINT NOT NULL, 
	PRIMARY KEY (user_id, student_id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE ent_auth_session (
	id VARCHAR(36) NOT NULL, 
	user_id BIGINT NOT NULL, 
	expires_at DATETIME NOT NULL, 
	revoked_at DATETIME, 
	create_time DATETIME NOT NULL, 
	PRIMARY KEY (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE ent_auth_login_attempt (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	attempt_key VARCHAR(64) NOT NULL, 
	create_time DATETIME NOT NULL, 
	PRIMARY KEY (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE ent_auth_audit (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	actor_id BIGINT, 
	action VARCHAR(64) NOT NULL, 
	target VARCHAR(128), 
	details TEXT NOT NULL, 
	create_time DATETIME NOT NULL, 
	PRIMARY KEY (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE ent_ai_conversation (
	id VARCHAR(36) NOT NULL, 
	employee_id BIGINT NOT NULL, 
	title VARCHAR(128) NOT NULL, 
	pending TEXT NOT NULL, 
	version INTEGER NOT NULL, 
	busy_token VARCHAR(36), 
	busy_until DATETIME, 
	create_time DATETIME NOT NULL, 
	update_time DATETIME NOT NULL, 
	PRIMARY KEY (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;

CREATE TABLE ent_ai_message (
	id BIGINT NOT NULL AUTO_INCREMENT, 
	conversation_id VARCHAR(36) NOT NULL, 
	`role` VARCHAR(16) NOT NULL, 
	content TEXT NOT NULL, 
	metadata_json TEXT NOT NULL, 
	create_time DATETIME NOT NULL, 
	PRIMARY KEY (id)
)ENGINE=InnoDB CHARSET=utf8mb4 COLLATE utf8mb4_unicode_ci;