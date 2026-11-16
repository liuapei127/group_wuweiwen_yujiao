-- Limit the built-in system administrator to administration and shared work tools.
START TRANSACTION;

DELETE grant_row
FROM ent_auth_role_permission AS grant_row
JOIN sys_role AS role_row ON role_row.id = grant_row.role_id
WHERE role_row.role_code = 'admin'
  AND grant_row.permission NOT IN (
      'dashboard:read', 'ai:use', 'directory:read', 'todos:read', 'todos:write', 'notifications:read',
      'events:manage', 'events:check_in', 'courses:manage', 'website-content:manage', 'website-accounts:manage',
      'organizations:manage', 'users:manage', 'roles:manage', 'audit:read'
  );

INSERT INTO ent_auth_role_permission (role_id, permission)
SELECT r.id, baseline.permission
FROM sys_role AS r
JOIN (
    SELECT 'employee' AS role_code, 'visitor-intake:read' AS permission
    UNION ALL SELECT 'employee', 'visitor-intake:write'
    UNION ALL SELECT 'manager', 'reports:operations:read'
    UNION ALL SELECT 'manager', 'reports:summary:read'
    UNION ALL SELECT 'manager', 'reports:formal:generate'
) AS baseline ON baseline.role_code = r.role_code
ON DUPLICATE KEY UPDATE permission = ent_auth_role_permission.permission;

COMMIT;
