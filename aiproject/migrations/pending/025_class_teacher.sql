-- Apply once after 023_project_classes.sql and before starting the updated backend.
-- Existing classes keep their former teacher assignment during the transition.
-- teaching_project.teacher_id is retained for the migration history; runtime uses project_class.teacher_id.
ALTER TABLE teaching_project MODIFY COLUMN teacher_id BIGINT UNSIGNED NULL;

ALTER TABLE project_class ADD COLUMN teacher_id BIGINT UNSIGNED NULL AFTER project_id;

UPDATE project_class AS class
JOIN teaching_project AS project ON project.project_id = class.project_id
SET class.teacher_id = project.teacher_id
WHERE class.teacher_id IS NULL;

ALTER TABLE project_class
  MODIFY COLUMN teacher_id BIGINT UNSIGNED NOT NULL,
  ADD KEY idx_project_class_teacher (teacher_id),
  ADD CONSTRAINT fk_project_class_teacher FOREIGN KEY (teacher_id) REFERENCES sys_user(id);
