-- Apply once after 025_class_teacher.sql.
CREATE TABLE IF NOT EXISTS teaching_course (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(128) NOT NULL,
  study_stage VARCHAR(16) NOT NULL,
  institution VARCHAR(128) NULL,
  enabled BOOLEAN NOT NULL,
  CONSTRAINT ck_teaching_course_stage CHECK (study_stage IN ('preparatory','language','overseas'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS class_course (
  class_id BIGINT UNSIGNED NOT NULL,
  course_id BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (class_id,course_id),
  FOREIGN KEY (class_id) REFERENCES project_class(id),
  FOREIGN KEY (course_id) REFERENCES teaching_course(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS class_placement_history (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  student_id BIGINT UNSIGNED NOT NULL,
  from_class_id BIGINT UNSIGNED NULL,
  to_class_id BIGINT UNSIGNED NOT NULL,
  actor_id BIGINT UNSIGNED NOT NULL,
  reason VARCHAR(1000) NOT NULL,
  changed_at DATETIME NOT NULL,
  KEY idx_class_placement_student(student_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS academic_class_batch (
  id VARCHAR(36) NOT NULL PRIMARY KEY,
  class_id BIGINT NOT NULL,
  actor_id BIGINT NOT NULL,
  payload_hash VARCHAR(64) NOT NULL,
  student_count INT NOT NULL,
  created_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS student_leave_attachment (
  id VARCHAR(36) NOT NULL PRIMARY KEY,
  student_id BIGINT NOT NULL,
  filename VARCHAR(255) NOT NULL,
  content_type VARCHAR(64) NOT NULL,
  content MEDIUMBLOB NOT NULL,
  created_at DATETIME NOT NULL,
  KEY idx_leave_attachment_student(student_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE student_score
  ADD COLUMN course_id BIGINT NULL,
  ADD COLUMN study_stage VARCHAR(16) NOT NULL DEFAULT 'unspecified';
ALTER TABLE academic_deadline ADD COLUMN study_stage VARCHAR(16) NOT NULL DEFAULT 'unspecified';

INSERT IGNORE INTO ent_auth_role_permission(role_id,permission)
SELECT role.id, grant_codes.code FROM sys_role AS role
JOIN (
  SELECT 'students:read' code UNION ALL SELECT 'scores:read' UNION ALL SELECT 'scores:write'
  UNION ALL SELECT 'leaves:read' UNION ALL SELECT 'leaves:approve'
  UNION ALL SELECT 'tickets:read' UNION ALL SELECT 'tickets:write'
  UNION ALL SELECT 'academics:read' UNION ALL SELECT 'academics:write'
  UNION ALL SELECT 'applications:read' UNION ALL SELECT 'applications:write'
  UNION ALL SELECT 'student-alerts:read' UNION ALL SELECT 'student-alerts:write'
) AS grant_codes
WHERE role.role_code IN ('team_leader','teacher');

INSERT IGNORE INTO ent_auth_role_permission(role_id,permission)
SELECT id,'applications:read' FROM sys_role WHERE role_code IN ('employee','advisor');
DELETE grant_row FROM ent_auth_role_permission AS grant_row
JOIN sys_role AS role ON role.id=grant_row.role_id
WHERE role.role_code IN ('employee','advisor') AND grant_row.permission='applications:write';

INSERT IGNORE INTO ent_auth_role_permission(role_id,permission)
SELECT id,'teaching:manage' FROM sys_role WHERE role_code='admin';
INSERT IGNORE INTO ent_auth_role_permission(role_id,permission)
SELECT id,'tickets:route' FROM sys_role WHERE role_code IN ('admin','manager');
