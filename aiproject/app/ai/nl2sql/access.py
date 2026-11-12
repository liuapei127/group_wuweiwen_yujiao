"""Bind whitelisted queries to the authenticated employee's data scope."""

class Nl2SqlSecurityError(Exception):
    pass


def require_identity(actor_employee_id):
    if not actor_employee_id or actor_employee_id < 1:
        raise Nl2SqlSecurityError("缺少可信员工身份")


def bind_employee_scope(intent, params, actor_employee_id):
    params = dict(params)
    for key in ("owner_employee_id", "employee_id"):
        if key in params and (type(params[key]) is not int or params[key] != actor_employee_id):
            raise Nl2SqlSecurityError("无权查询其他员工数据")
    if intent.startswith("lead"):
        params["owner_employee_id"] = actor_employee_id
    if intent == "daily_reports_recent":
        params["employee_id"] = actor_employee_id
    if intent == "pending_leaves":
        params["approver_id"] = actor_employee_id
    return params
