-- Existing event tables only. Keep user_id and legacy registration data intact.
ALTER TABLE event_registration
    ADD COLUMN customer_id BIGINT NULL,
    ADD COLUMN cancelled_at DATETIME NULL,
    ADD COLUMN attended_at DATETIME NULL,
    ADD COLUMN checked_in_by BIGINT NULL,
    ADD CONSTRAINT uq_event_customer UNIQUE (event_id, customer_id);
