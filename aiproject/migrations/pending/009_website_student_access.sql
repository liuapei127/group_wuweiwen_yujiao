-- Apply after 006; sys_user must already exist.
CREATE TABLE website_student_access (
    visitor_id BIGINT NOT NULL,
    student_id BIGINT UNSIGNED NOT NULL,
    enabled BOOLEAN NOT NULL,
    PRIMARY KEY (visitor_id),
    CONSTRAINT uq_website_student_access UNIQUE (student_id),
    FOREIGN KEY (visitor_id) REFERENCES visitor_account (id),
    FOREIGN KEY (student_id) REFERENCES sys_user (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
