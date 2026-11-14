-- 依赖 008 以及原有 crm_lead 表。
ALTER TABLE visitor_intake
    ADD COLUMN crm_lead_id BIGINT UNSIGNED NULL,
    ADD UNIQUE KEY uq_visitor_intake_crm (crm_lead_id),
    ADD CONSTRAINT fk_visitor_intake_crm FOREIGN KEY (crm_lead_id) REFERENCES crm_lead (id);
