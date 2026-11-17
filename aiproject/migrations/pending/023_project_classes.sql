CREATE TABLE IF NOT EXISTS teaching_project (
  project_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
  teacher_id BIGINT UNSIGNED NOT NULL,
  abroad_country VARCHAR(16) NOT NULL,
  KEY idx_teaching_project_teacher (teacher_id),
  CONSTRAINT fk_teaching_project_catalog FOREIGN KEY (project_id) REFERENCES course_project(id),
  CONSTRAINT fk_teaching_project_teacher FOREIGN KEY (teacher_id) REFERENCES sys_user(id),
  CONSTRAINT ck_teaching_project_country CHECK (abroad_country IN ('Singapore', 'Germany'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS project_class (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  project_id BIGINT UNSIGNED NOT NULL,
  name VARCHAR(100) NOT NULL,
  enabled BOOLEAN NOT NULL,
  CONSTRAINT uq_project_class_name UNIQUE (project_id, name),
  CONSTRAINT fk_project_class_project FOREIGN KEY (project_id) REFERENCES teaching_project(project_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS student_class_enrollment (
  student_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
  class_id BIGINT UNSIGNED NOT NULL,
  KEY idx_class_enrollment_class (class_id),
  CONSTRAINT fk_class_enrollment_student FOREIGN KEY (student_id) REFERENCES student_info(user_id),
  CONSTRAINT fk_class_enrollment_class FOREIGN KEY (class_id) REFERENCES project_class(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO ent_auth_role_permission (role_id, permission)
SELECT id, 'classes:manage' FROM sys_role WHERE role_code = 'admin'
ON DUPLICATE KEY UPDATE permission = 'classes:manage';
