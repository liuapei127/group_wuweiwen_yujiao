CREATE TABLE IF NOT EXISTS crm_lead_status_event (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
 lead_id BIGINT NOT NULL, status VARCHAR(16) NOT NULL, occurred_at DATETIME NOT NULL, reason VARCHAR(255),
 KEY ix_lead_status_event_period (status, occurred_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS report_status_history_start (
 id INT NOT NULL PRIMARY KEY, start_day DATE NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
INSERT INTO report_status_history_start (id,start_day)
VALUES (1,DATE(DATE_ADD(UTC_TIMESTAMP(), INTERVAL 8 HOUR)))
ON DUPLICATE KEY UPDATE id=id;
CREATE TABLE IF NOT EXISTS report_wellbeing_consent (
 student_id BIGINT NOT NULL PRIMARY KEY, granted BOOLEAN NOT NULL, version VARCHAR(16) NOT NULL, updated_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS report_wellbeing_checkin (
 student_id BIGINT NOT NULL, day DATE NOT NULL, emotion VARCHAR(16) NOT NULL, stress VARCHAR(16) NOT NULL,
 updated_at DATETIME NOT NULL, PRIMARY KEY (student_id,day)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS report_wellbeing_case (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, student_id BIGINT NOT NULL, status VARCHAR(16) NOT NULL,
 note TEXT NOT NULL, assigned_to BIGINT, created_at DATETIME NOT NULL, KEY ix_report_care_student_status (student_id,status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS report_wellbeing_followup (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, case_id BIGINT NOT NULL, actor_id BIGINT NOT NULL,
 note TEXT NOT NULL, created_at DATETIME NOT NULL, KEY ix_report_care_followup_case (case_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS report_wellbeing_event (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, employee_id BIGINT NOT NULL, title VARCHAR(100) NOT NULL,
 day DATE NOT NULL, note TEXT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS employee_weekly_submission (
 employee_id BIGINT NOT NULL, week_start DATE NOT NULL, content TEXT NOT NULL,
 key_progress TEXT, risks TEXT, next_plan TEXT, submitted_at DATETIME NOT NULL,
 PRIMARY KEY (employee_id,week_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
CREATE TABLE IF NOT EXISTS report_employee_conflict (
 id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY, employee_id BIGINT NOT NULL, week_start DATE NOT NULL,
 summary VARCHAR(512) NOT NULL, daily_excerpt TEXT NOT NULL, weekly_excerpt TEXT NOT NULL, status VARCHAR(16) NOT NULL,
 verify_note TEXT, KEY ix_report_employee_conflict_week (employee_id,week_start)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
