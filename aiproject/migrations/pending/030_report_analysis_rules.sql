CREATE TABLE IF NOT EXISTS report_analysis_rules (
    id INT NOT NULL PRIMARY KEY,
    version INT NOT NULL,
    settings JSON NOT NULL,
    updated_by BIGINT NOT NULL,
    updated_at DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS report_schedule_options (
    schedule_id BIGINT NOT NULL PRIMARY KEY,
    include_ai BOOLEAN NOT NULL DEFAULT FALSE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS report_rule_signal (
    `key` VARCHAR(128) NOT NULL PRIMARY KEY,
    kind VARCHAR(32) NOT NULL,
    related_id BIGINT NOT NULL,
    rule_version INT NOT NULL,
    created_at DATETIME NOT NULL,
    INDEX ix_report_rule_signal_kind (kind)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
