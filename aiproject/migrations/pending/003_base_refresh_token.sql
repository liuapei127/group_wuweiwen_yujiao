-- DO NOT EXECUTE against education_service until this DDL is approved.
-- BASE refresh sessions. Does not add ent_auth_session.signing_kid.
-- Existing ENT inserts list their columns and leave the new columns NULL.

ALTER TABLE ent_auth_session
  ADD COLUMN last_used_at DATETIME NULL,
  ADD COLUMN parent_session_id VARCHAR(36) NULL;

CREATE TABLE auth_refresh_token (
  token_hash CHAR(64) NOT NULL,
  family_id VARCHAR(36) NOT NULL,
  session_id VARCHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  user_id BIGINT UNSIGNED NOT NULL,
  expires_at DATETIME NOT NULL,
  used_at DATETIME NULL,
  revoked_at DATETIME NULL,
  replaced_by CHAR(64) NULL,
  PRIMARY KEY (token_hash),
  KEY idx_refresh_family (family_id),
  KEY idx_refresh_session (session_id),
  KEY idx_refresh_user (user_id),
  CONSTRAINT fk_refresh_session FOREIGN KEY (session_id) REFERENCES ent_auth_session (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE auth_user_session_kid (
  session_id VARCHAR(36) CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci NOT NULL,
  kid VARCHAR(64) NOT NULL,
  first_issued_at DATETIME NOT NULL,
  PRIMARY KEY (session_id, kid),
  KEY idx_user_session_kid (kid),
  CONSTRAINT fk_user_session_kid FOREIGN KEY (session_id) REFERENCES ent_auth_session (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
