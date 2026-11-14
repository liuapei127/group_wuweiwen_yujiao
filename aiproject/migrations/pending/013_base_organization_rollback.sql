-- Reverses organization storage. Back up assignments and history before use.
DROP TRIGGER trg_user_before_update;
DROP TRIGGER trg_member_before_insert;
DROP TRIGGER trg_member_before_update;
DROP TRIGGER trg_member_after_insert;
DROP TABLE sys_org_member_history;
DROP TABLE sys_user_primary_org;
DROP TABLE sys_org_member;
