-- DO NOT EXECUTE until the forward DDL was applied and rollback is approved.
-- Drops only the BASE refresh objects. Does not drop ent_auth_session or its original columns.

DROP TABLE IF EXISTS auth_user_session_kid;
DROP TABLE IF EXISTS auth_refresh_token;

ALTER TABLE ent_auth_session
  DROP COLUMN parent_session_id,
  DROP COLUMN last_used_at;
