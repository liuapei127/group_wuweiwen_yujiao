-- Grant manager access to the school-wide aggregated wellbeing weekly report.
INSERT INTO ent_auth_role_permission (role_id, permission)
SELECT id, 'reports:wellbeing:read'
FROM sys_role
WHERE role_code = 'manager'
ON DUPLICATE KEY UPDATE permission = ent_auth_role_permission.permission;
