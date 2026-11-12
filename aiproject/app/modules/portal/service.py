from app.core.config import get_settings
from app.core.security.rbac import ACTION_PERMISSIONS,INTENT_PERMISSIONS,permission_catalog
from app.ai.workflows.ent_contracts import ACTIONS
from app.modules.auth.service import AuthService
from app.modules.auth.repository import AuthRepository
from .repository import PortalRepository

FEATURES=[
 ('dashboard','工作台','/dashboard','dashboard:read'),('customers','客户管理','/customers','crm:read'),
 ('reports','员工日报','/reports','reports:read'),('directory','组织与同事','/directory','directory:read'),
 ('guides','新人指南','/guides','guides:read'),('scores','学生成绩','/scores','scores:read'),
 ('leaves','请假审批','/leaves','leaves:read'),('tickets','投诉工单','/tickets','tickets:read'),
 ('todos','我的待办','/todos','todos:read'),('notifications','站内通知','/notifications','notifications:read'),
 ('queries','智能查询','/queries','queries:read'),('commands','业务指令','/commands','commands:execute'),
 ('assistant','AI助手','/assistant','ai:use'),('users','员工管理','/settings/users','users:manage'),
 ('roles','角色权限','/settings/roles','roles:manage'),('audit','安全审计','/settings/audit','audit:read')]

class PortalService:
    def __init__(self,db):self.db=db

    def context(self,p):
        return {'user':AuthService(self.db).me(p),'counters':PortalRepository(self.db).counters(p),
            'features':[{'key':k,'title':t,'path':path,'permission':permission} for k,t,path,permission in FEATURES if permission in p.permissions],
            'actions':[{'code':a,'method':v[0].upper(),'path':v[1],'required':v[2].split(),'allowed':v[3].split(),
                        'permission':ACTION_PERMISSIONS[a]} for a,v in ACTIONS.items() if ACTION_PERMISSIONS[a] in p.permissions],
            'query_intents':[i for i,perm in INTENT_PERMISSIONS.items() if perm in p.permissions],
            'permissions':[v for v in permission_catalog() if v['code'] in p.permissions]}

    def students(self,p):
        return AuthRepository(self.db).students(p.student_ids)

    def health(self):
        settings=get_settings()
        return {'backend':'ok','database':'connected' if PortalRepository(self.db).database_ready() else 'unavailable',
                'employee_identity_mode':settings.employee_identity_mode,
                'ai_configured':bool(settings.dify_workflow_api_key.get_secret_value()),
                'ai_engine':'Dify 参数理解工作流','business_authorization':'RBAC + 本人归属 + 学生授权范围'}
