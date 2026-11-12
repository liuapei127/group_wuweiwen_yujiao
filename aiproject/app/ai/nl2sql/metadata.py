"""只读查询意图元数据（白名单）。"""

MAX_ROWS = 50

ALLOWED_INTENTS: dict[str, dict] = {
    "lead_detail_by_name": {
        "description": "按客户姓名查档案",
        "params": ["customer_name"],
        "tables": ["crm_lead"],
    },
    "lead_follow_ups_by_name": {
        "description": "按客户姓名查跟进记录",
        "params": ["customer_name"],
        "tables": ["crm_lead", "crm_follow_up"],
    },
    "leads_by_status": {
        "description": "按状态查意向客户列表",
        "params": ["status"],
        "optional_params": ["owner_employee_id"],
        "tables": ["crm_lead"],
    },
    "pending_leaves": {
        "description": "待审批请假列表",
        "params": [],
        "tables": ["student_admin_service"],
    },
    "daily_reports_recent": {
        "description": "近期员工日报",
        "params": [],
        "optional_params": ["employee_id"],
        "tables": ["employee_daily_report"],
    },
}

READ_ONLY_TABLES = frozenset(
    {
        "crm_lead",
        "crm_follow_up",
        "employee_daily_report",
        "student_admin_service",
    }
)
