import {AppstoreOutlined,TeamOutlined,FileTextOutlined,ApartmentOutlined,BookOutlined,TrophyOutlined,AuditOutlined,CustomerServiceOutlined,CheckSquareOutlined,BellOutlined,SearchOutlined,ThunderboltOutlined,RobotOutlined,SafetyCertificateOutlined,UserOutlined,HistoryOutlined} from '@ant-design/icons'
export const navigation=[
 {path:'/dashboard',title:'工作台',permission:'dashboard:read',icon:<AppstoreOutlined/>},
 {path:'/assistant',title:'AI 助手',permission:'ai:use',icon:<RobotOutlined/>},
 {path:'/customers',title:'客户管理',permission:'crm:read',icon:<TeamOutlined/>},
 {path:'/reports',title:'员工日报',permission:'reports:read',icon:<FileTextOutlined/>},
 {path:'/directory',title:'组织与同事',permission:'directory:read',icon:<ApartmentOutlined/>},
 {path:'/guides',title:'新人指南',permission:'guides:read',icon:<BookOutlined/>},
 {path:'/scores',title:'学生成绩',permission:'scores:read',icon:<TrophyOutlined/>},
 {path:'/leaves',title:'请假审批',permission:'leaves:read',icon:<AuditOutlined/>},
 {path:'/tickets',title:'投诉工单',permission:'tickets:read',icon:<CustomerServiceOutlined/>},
 {path:'/todos',title:'我的待办',permission:'todos:read',icon:<CheckSquareOutlined/>},
 {path:'/notifications',title:'站内通知',permission:'notifications:read',icon:<BellOutlined/>},
 {path:'/queries',title:'智能查询',permission:'queries:read',icon:<SearchOutlined/>},
 {path:'/commands',title:'业务指令',permission:'commands:execute',icon:<ThunderboltOutlined/>},
 {path:'/settings/users',title:'员工管理',permission:'users:manage',icon:<UserOutlined/>},
 {path:'/settings/roles',title:'角色权限',permission:'roles:manage',icon:<SafetyCertificateOutlined/>},
 {path:'/settings/audit',title:'安全审计',permission:'audit:read',icon:<HistoryOutlined/>},
]
export const permissionNames:Record<string,string>={
 'dashboard:read':'工作台','crm:read':'查看本人客户','crm:write':'维护本人客户','reports:read':'查看本人日报','reports:write':'提交本人日报',
 'directory:read':'组织与同事查询','directory:contacts':'查看同事联系方式','guides:read':'查询指南','guides:write':'新增指南',
 'scores:read':'查询授权学生成绩','scores:write':'录入与更正成绩','leaves:read':'查询本人待审批请假','leaves:approve':'审批请假',
 'tickets:read':'查看本人工单','tickets:write':'处理本人工单','todos:read':'查看本人待办','todos:write':'维护本人待办',
 'notifications:read':'查看本人通知','queries:read':'白名单查询','commands:execute':'业务指令','ai:use':'AI助手',
 'users:manage':'管理员工','roles:manage':'配置角色权限','audit:read':'查看安全审计'}
