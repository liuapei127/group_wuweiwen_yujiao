"""Server-owned RBAC catalogue shared by menus, route checks and AI actions."""
from app.core.exceptions import BusinessError

PERMISSIONS = {
    'dashboard:read': ('工作台', '工作台'),
    'crm:read': ('查询本人客户、详情和跟进', '客户管理'),
    'crm:write': ('创建、修改客户及跟进', '客户管理'),
    'reports:read': ('查询本人日报', '员工日报'),
    'reports:write': ('提交本人日报', '员工日报'),
    'directory:read': ('查询组织与同事', '组织目录'),
    'directory:contacts': ('查看同事联系方式', '组织目录'),
    'guides:read': ('查询新人指南', '新人指南'),
    'guides:write': ('创建新人指南', '新人指南'),
    'scores:read': ('查询授权学生成绩与历史', '成绩管理'),
    'scores:write': ('录入和更正授权学生成绩', '成绩管理'),
    'leaves:read': ('查询分配给本人的待审批请假', '请假审批'),
    'leaves:approve': ('审批分配给本人的请假', '请假审批'),
    'tickets:read': ('查询分配给本人的工单', '投诉工单'),
    'tickets:write': ('处理分配给本人的工单', '投诉工单'),
    'todos:read': ('查询本人待办', '我的待办'),
    'todos:write': ('创建和处理本人待办', '我的待办'),
    'notifications:read': ('查看本人通知', '站内通知'),
    'queries:read': ('执行已有权限范围内的白名单查询', '智能查询'),
    'commands:execute': ('执行已有权限范围内的结构化指令', '业务指令'),
    'ai:use': ('使用AI助手，操作受同一业务权限保护', 'AI助手'),
    'users:manage': ('管理员工账号、角色分配和学生授权', '员工管理'),
    'roles:manage': ('管理角色和功能权限', '角色权限'),
    'audit:read': ('查看认证与权限变更审计', '安全审计'),
}
COMMON = {'dashboard:read','reports:read','reports:write','directory:read','guides:read',
          'tickets:read','tickets:write','todos:read','todos:write','notifications:read',
          'queries:read','commands:execute','ai:use'}
ROLE_DEFAULTS = {
    'admin': set(PERMISSIONS),
    'employee': COMMON | {'crm:read','crm:write'},
    'manager': COMMON | {'crm:read','crm:write','directory:contacts','guides:write'},
    'team_leader': COMMON | {'directory:contacts','scores:read','scores:write','leaves:read','leaves:approve'},
    'student': set(),
}
INTENT_PERMISSIONS = {
    'leads_by_status':'crm:read', 'lead_detail_by_name':'crm:read',
    'lead_follow_ups_by_name':'crm:read', 'pending_leaves':'leaves:read',
    'daily_reports_recent':'reports:read',
}
ACTION_PERMISSIONS = {
    'lead_create':'crm:write','lead_list':'crm:read','lead_detail':'crm:read',
    'lead_update':'crm:write','lead_status':'crm:write','lead_follow_up':'crm:write',
    'daily_submit':'reports:write','daily_list':'reports:read','organizations':'directory:read',
    'colleagues':'directory:read','colleague_contact':'directory:contacts','guides':'guides:read',
    'guide_create':'guides:write','score_create':'scores:write','scores':'scores:read',
    'score_correct':'scores:write','score_history':'scores:read','leaves':'leaves:read',
    'leave_approve':'leaves:approve','tickets':'tickets:read','ticket_detail':'tickets:read',
    'ticket_update':'tickets:write','todos':'todos:read','todo_create':'todos:write',
    'todo_update':'todos:write','notifications':'notifications:read','nl_query':'queries:read',
}


def route_permission(method, path):
    from app.ai.workflows.ent_contracts import ACTIONS
    routes = {(m.upper(), p): ACTION_PERMISSIONS[a] for a,(m,p,*_) in ACTIONS.items()}
    routes.update({
        ('POST','/api/v1/enterprise/commands'):'commands:execute',
        ('GET','/api/v1/auth/me'):None, ('POST','/api/v1/auth/logout'):None,
        ('POST','/api/v1/auth/password'):None,
        ('GET','/api/v1/auth/users'):'users:manage', ('POST','/api/v1/auth/users'):'users:manage',
        ('PATCH','/api/v1/auth/users/{user_id}'):'users:manage',
        ('PUT','/api/v1/auth/users/{user_id}/student-scope'):'users:manage',
        ('POST','/api/v1/auth/users/{user_id}/password'):'users:manage',
        ('GET','/api/v1/auth/roles'):'roles:manage', ('POST','/api/v1/auth/roles'):'roles:manage',
        ('PUT','/api/v1/auth/roles/{role_id}'):'roles:manage',
        ('GET','/api/v1/auth/permissions'):'roles:manage',
        ('GET','/api/v1/auth/audit'):'audit:read',
        ('GET','/api/v1/auth/students'):'users:manage',
        ('GET','/api/v1/portal/context'):'dashboard:read',
        ('GET','/api/v1/portal/students'):'scores:read',
        ('GET','/api/v1/portal/health'):'dashboard:read',
        ('GET','/api/v1/ai/assistant/conversations'):'ai:use',
        ('POST','/api/v1/ai/assistant/conversations'):'ai:use',
        ('GET','/api/v1/ai/assistant/conversations/{conversation_id}'):'ai:use',
        ('POST','/api/v1/ai/assistant/conversations/{conversation_id}/messages'):'ai:use',
    })
    key = (method.upper(), path)
    if key not in routes:
        raise BusinessError(403, '此接口尚未配置访问权限')
    return routes[key]


def permission_catalog():
    return [{'code':k,'name':v[0],'group':v[1]} for k,v in PERMISSIONS.items()]
