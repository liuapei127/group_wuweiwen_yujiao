-- Apply once after 026, to the explicitly selected deployment database.
-- Existing business records and conversations are preserved.
CREATE TABLE IF NOT EXISTS stu_assistant_task (
  id VARCHAR(36) NOT NULL PRIMARY KEY,
  student_id BIGINT NOT NULL,
  conversation_id VARCHAR(36) NOT NULL,
  kind VARCHAR(24) NOT NULL,
  ordinal INT NOT NULL DEFAULT 1,
  status VARCHAR(32) NOT NULL,
  payload JSON NOT NULL,
  result JSON NULL,
  version INT NOT NULL DEFAULT 1,
  expires_at DATETIME NOT NULL,
  create_time DATETIME NOT NULL,
  update_time DATETIME NOT NULL,
  KEY ix_stu_task_student (student_id),
  KEY ix_stu_task_conversation (conversation_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE overseas_life_knowledge
  MODIFY COLUMN category ENUM('medical','transport','emergency','daily_life','other','arrival','housing','study') NOT NULL,
  ADD COLUMN city VARCHAR(128) NULL,
  ADD COLUMN source_title VARCHAR(255) NULL,
  ADD COLUMN source_url VARCHAR(1028) NULL,
  ADD COLUMN verified_at DATE NULL;
