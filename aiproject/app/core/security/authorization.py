from app.core.exceptions import BusinessError


def require_permission(principal, permission):
    if permission not in principal.permissions:
        raise BusinessError(403, "缺少操作权限")


def require_student_scope(principal, student_id, permission):
    require_permission(principal, permission)
    if student_id not in principal.student_ids:
        raise BusinessError(403, "学生不在授权范围")


def require_owned(record, employee_id, column):
    if record is None:
        raise BusinessError(404, "记录不存在")
    if record[column] != employee_id:
        raise BusinessError(403, "无权访问此记录")
    return record
