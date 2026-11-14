-- 活动表如已存在，部署前核对旧结构和数据迁移。

CREATE TABLE event_lecture (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	event_type ENUM('online','offline','hybrid') NOT NULL DEFAULT 'offline',
	status ENUM('upcoming','ongoing','ended','cancelled') NOT NULL DEFAULT 'upcoming',
	event_name VARCHAR(255) NOT NULL,
	description TEXT,
	start_time DATETIME NOT NULL,
	end_time DATETIME NOT NULL,
	location VARCHAR(255) NOT NULL,
	max_participants INTEGER NOT NULL,
	current_participants INTEGER NOT NULL,
	organizer_id BIGINT NOT NULL,
	create_time DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT ck_event_capacity_positive CHECK (max_participants > 0),
	CONSTRAINT ck_event_capacity_used CHECK (current_participants BETWEEN 0 AND max_participants)
)ENGINE=InnoDB CHARSET=utf8mb4;

CREATE TABLE event_registration (
	id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
	event_id BIGINT UNSIGNED NOT NULL,
	customer_id BIGINT NULL,
	status ENUM('registered','cancelled','attended','no_show') NOT NULL,
	create_time DATETIME NOT NULL,
	cancelled_at DATETIME,
	attended_at DATETIME,
	checked_in_by BIGINT,
	PRIMARY KEY (id),
	CONSTRAINT uq_event_customer UNIQUE (event_id, customer_id),
	FOREIGN KEY(event_id) REFERENCES event_lecture (id)
)ENGINE=InnoDB CHARSET=utf8mb4;
