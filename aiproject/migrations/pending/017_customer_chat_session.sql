CREATE TABLE IF NOT EXISTS cs_website_session (
    id VARCHAR(64) NOT NULL,
    visitor_id BIGINT NULL,
    expires_at DATETIME NOT NULL,
    dify_conversation_id VARCHAR(64) NULL,
    previous_query VARCHAR(1200) NULL,
    event_options JSON NULL,
    pending_event_id BIGINT NULL,
    PRIMARY KEY (id),
    KEY ix_cs_website_session_visitor_id (visitor_id),
    KEY ix_cs_website_session_expires_at (expires_at),
    FOREIGN KEY (visitor_id) REFERENCES visitor_account (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
