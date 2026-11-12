-- Expected post-migration definitions; not a destructive replacement script.

CREATE TABLE `student_score` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `student_id`        BIGINT UNSIGNED NOT NULL                COMMENT '学生ID（关联sys_user）',
    `course_name`       VARCHAR(128)    NOT NULL                COMMENT '课程名称',
    `score`             DECIMAL(5,2)    NOT NULL                COMMENT '成绩',
    `semester`          VARCHAR(32)     DEFAULT NULL            COMMENT '学期（如 2025-2026-1）',
    `credit`            DECIMAL(3,1)    DEFAULT NULL            COMMENT '学分',
    `recorded_by`       BIGINT UNSIGNED DEFAULT NULL            COMMENT '录入人ID',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `exam_key` VARCHAR(96) DEFAULT NULL,
    `submission_key` VARCHAR(96) DEFAULT NULL,
    `submission_hash` VARCHAR(64) DEFAULT NULL,
    `version` INT NOT NULL DEFAULT 1,
    `update_time` DATETIME DEFAULT NULL,
    UNIQUE KEY `uk_score_exam` (`student_id`,`exam_key`),
    UNIQUE KEY `uk_score_submission` (`student_id`,`submission_key`),
    PRIMARY KEY (`id`),
    KEY `idx_student_id` (`student_id`),
    KEY `idx_semester` (`semester`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='学生成绩表';

CREATE TABLE `todo_item` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `assignee_id`       BIGINT UNSIGNED NOT NULL                COMMENT '指派人ID',
    `todo_type`         ENUM('leave_approval','complaint_follow','report_remind','custom') NOT NULL COMMENT '待办类型',
    `title`             VARCHAR(255)    NOT NULL                COMMENT '待办标题',
    `description`       TEXT            DEFAULT NULL            COMMENT '待办描述',
    `related_type`      VARCHAR(64)     DEFAULT NULL            COMMENT '关联业务类型',
    `related_id`        BIGINT UNSIGNED DEFAULT NULL            COMMENT '关联业务ID',
    `priority`          ENUM('low','medium','high','urgent') NOT NULL DEFAULT 'medium' COMMENT '优先级',
    `status`            ENUM('pending','in_progress','done','cancelled') NOT NULL DEFAULT 'pending' COMMENT '状态',
    `due_time`          DATETIME        DEFAULT NULL            COMMENT '截止时间',
    `completed_time`    DATETIME        DEFAULT NULL            COMMENT '完成时间',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `update_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    `assignment_version` INT NOT NULL DEFAULT 1,
    `source_status` VARCHAR(32) DEFAULT NULL,
    UNIQUE KEY `uk_todo_source` (`related_type`,`related_id`),
    PRIMARY KEY (`id`),
    KEY `idx_assignee` (`assignee_id`),
    KEY `idx_status` (`status`),
    KEY `idx_todo_type` (`todo_type`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='待办事项表';

CREATE TABLE `notification_log` (
    `id`                BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '主键',
    `user_id`           BIGINT UNSIGNED NOT NULL                COMMENT '接收人ID',
    `notification_type` VARCHAR(64)     NOT NULL                COMMENT '通知类型',
    `related_type`      VARCHAR(64)     DEFAULT NULL            COMMENT '关联业务类型',
    `related_id`        BIGINT UNSIGNED DEFAULT NULL            COMMENT '关联业务ID',
    `title`             VARCHAR(255)    NOT NULL                COMMENT '通知标题',
    `content`           TEXT            NOT NULL                COMMENT '通知内容',
    `channel`           ENUM('system','email','sms','wechat') NOT NULL DEFAULT 'system' COMMENT '通知渠道',
    `status`            ENUM('pending','sent','failed') NOT NULL DEFAULT 'pending' COMMENT '发送状态',
    `error_message`     TEXT            DEFAULT NULL            COMMENT '失败原因',
    `create_time`       DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
    `dedup_key` VARCHAR(128) DEFAULT NULL,
    UNIQUE KEY `uk_notification_dedup` (`dedup_key`),
    PRIMARY KEY (`id`),
    KEY `idx_user_id` (`user_id`),
    KEY `idx_status` (`status`),
    KEY `idx_create_time` (`create_time`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='提醒通知记录表';

CREATE TABLE `student_score_history` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    `score_id` BIGINT UNSIGNED NOT NULL,
    `version` INT NOT NULL,
    `operation` VARCHAR(16) NOT NULL,
    `changed_by` BIGINT UNSIGNED DEFAULT NULL,
    `change_reason` TEXT DEFAULT NULL,
    `before_data` JSON DEFAULT NULL,
    `after_data` JSON NOT NULL,
    `create_time` DATETIME NOT NULL,
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_score_history_version` (`score_id`,`version`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
