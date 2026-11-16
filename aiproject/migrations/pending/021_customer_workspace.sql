ALTER TABLE crm_lead
    ADD COLUMN intended_project VARCHAR(40) NULL,
    ADD COLUMN education_stage VARCHAR(24) NULL,
    ADD COLUMN profile_version INT NOT NULL DEFAULT 0;

ALTER TABLE customer_profile
    ADD COLUMN lead_id BIGINT UNSIGNED NULL,
    ADD COLUMN profile_version INT NULL,
    ADD KEY idx_customer_profile_lead (lead_id, id),
    ADD CONSTRAINT fk_customer_profile_lead FOREIGN KEY (lead_id) REFERENCES crm_lead (id);

ALTER TABLE customer_source
    ADD COLUMN lead_id BIGINT UNSIGNED NULL,
    ADD COLUMN file_content MEDIUMBLOB NULL,
    ADD CONSTRAINT fk_customer_source_lead FOREIGN KEY (lead_id) REFERENCES crm_lead (id);

CREATE TABLE crm_customer_identity (
    lead_id BIGINT UNSIGNED NOT NULL,
    verified_name VARCHAR(64) NOT NULL,
    verified_mobile VARCHAR(11) NOT NULL,
    verified_by BIGINT NOT NULL,
    verified_at DATETIME NOT NULL,
    PRIMARY KEY (lead_id),
    UNIQUE KEY uq_crm_customer_verified_mobile (verified_mobile),
    FOREIGN KEY (lead_id) REFERENCES crm_lead (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE crm_customer_import_preview (
    id VARCHAR(36) NOT NULL,
    lead_id BIGINT UNSIGNED NOT NULL,
    actor_kind VARCHAR(12) NOT NULL,
    actor_id BIGINT NOT NULL,
    profile_version INT NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    file_content MEDIUMBLOB NOT NULL,
    raw_content TEXT NOT NULL,
    proposed JSON NOT NULL,
    expires_at DATETIME NOT NULL,
    PRIMARY KEY (id),
    KEY idx_crm_import_preview_lead (lead_id),
    KEY idx_crm_import_preview_expiry (expires_at),
    FOREIGN KEY (lead_id) REFERENCES crm_lead (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

UPDATE crm_lead AS l
JOIN customer_profile AS p ON l.customer_profile_id = p.id
SET l.intended_project = COALESCE(l.intended_project, NULLIF(JSON_UNQUOTE(JSON_EXTRACT(p.background_info, '$.input.project')), 'null')),
    l.education_stage = COALESCE(l.education_stage, NULLIF(JSON_UNQUOTE(JSON_EXTRACT(p.background_info, '$.input.education_stage')), 'null'))
WHERE l.profile_version = 0;

UPDATE customer_profile AS p
JOIN crm_lead AS l ON l.customer_profile_id = p.id
SET p.lead_id = l.id, p.profile_version = 0
WHERE p.lead_id IS NULL;
