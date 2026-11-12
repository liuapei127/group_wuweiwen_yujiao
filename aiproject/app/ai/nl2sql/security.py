from app.ai.nl2sql.metadata import ALLOWED_INTENTS, MAX_ROWS


from app.ai.nl2sql.access import Nl2SqlSecurityError, require_identity, bind_employee_scope


def validate_request(intent: str, params: dict, actor_employee_id: int | None) -> dict:
    require_identity(actor_employee_id)
    meta = ALLOWED_INTENTS.get(intent)
    if not meta:
        raise Nl2SqlSecurityError("未授权的查询意图")
    allowed = set(meta.get("params", [])) | set(meta.get("optional_params", []))
    if set(params) - allowed:
        raise Nl2SqlSecurityError("包含未授权参数或 SQL 文本")
    for key in meta.get("params", []):
        if key not in params or params[key] in (None, ""):
            raise ValueError(f"缺少参数: {key}")
    params = bind_employee_scope(intent, params, actor_employee_id)
    if "customer_name" in params:
        name = params["customer_name"]
        if not isinstance(name, str) or not name.strip() or len(name) > 64:
            raise ValueError("客户姓名格式不正确")
        params["customer_name"] = name.strip()
    if intent == "leads_by_status" and params["status"] not in ("new", "contacting", "qualified", "signed", "lost"):
        raise ValueError("客户状态不合法")
    params["_max_rows"] = MAX_ROWS
    return params
