CREATE TABLE IF NOT EXISTS cs_short_turn (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    session_id VARCHAR(64) NOT NULL,
    role VARCHAR(16) NOT NULL,
    content VARCHAR(240) NOT NULL,
    created_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY ix_cs_short_turn_session_id (session_id),
    CONSTRAINT fk_cs_short_turn_session FOREIGN KEY (session_id) REFERENCES cs_website_session (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cs_visitor_profile (
    visitor_id BIGINT NOT NULL,
    display_name VARCHAR(32) NULL,
    destinations VARCHAR(64) NULL,
    education VARCHAR(16) NULL,
    education_stage VARCHAR(16) NULL,
    interests VARCHAR(128) NULL,
    attributes JSON NULL,
    summary VARCHAR(300) NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (visitor_id),
    CONSTRAINT fk_cs_visitor_profile_visitor FOREIGN KEY (visitor_id) REFERENCES visitor_account (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cs_visitor_memory (
    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
    visitor_id BIGINT NOT NULL,
    fact VARCHAR(200) NOT NULL,
    updated_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY ix_cs_visitor_memory_visitor_id (visitor_id),
    CONSTRAINT fk_cs_visitor_memory_visitor FOREIGN KEY (visitor_id) REFERENCES visitor_account (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
