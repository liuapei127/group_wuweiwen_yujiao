CREATE TABLE IF NOT EXISTS visitor_avatar (
    visitor_id BIGINT NOT NULL,
    image MEDIUMBLOB NOT NULL,
    PRIMARY KEY (visitor_id),
    FOREIGN KEY (visitor_id) REFERENCES visitor_account (id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
