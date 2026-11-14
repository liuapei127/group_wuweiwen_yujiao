import {CalendarOutlined,AppstoreOutlined,TeamOutlined,FileTextOutlined,ApartmentOutlined,BookOutlined,TrophyOutlined,AuditOutlined,CustomerServiceOutlined,CheckSquareOutlined,BellOutlined,SearchOutlined,ThunderboltOutlined,RobotOutlined,SafetyCertificateOutlined,UserOutlined,HistoryOutlined} from '@ant-design/icons'
export const navigation=[
 {path:'/dashboard',title:'工作台',permission:'dashboard:read',icon:<AppstoreOutlined/>},
 {path:'/assistant',title:'AI 助手',permission:'ai:use',icon:<RobotOutlined/>},
 {path:'/customers',title:'客户管理',permission:'crm:read',icon:<TeamOutlined/>},
 {path:'/visitor-intake',title:'游客跟进',permission:'visitor-intake:read',icon:<CustomerServiceOutlined/>},
 {path:'/reporting',title:'智报中心',permission:'reports:operations:read',alternatePermission:'reports:summary:read',extraPermission:'student-alerts:read',icon:<FileTextOutlined/>},
 {path:'/reports',title:'员工日报',permission:'reports:read',icon:<FileTextOutlined/>},
 {path:'/directory',title:'组织与同事',permission:'directory:read',icon:<ApartmentOutlined/>},
 {path:'/guides',title:'新人指南',permission:'guides:read',icon:<BookOutlined/>},
 {path:'/scores',title:'学生成绩',permission:'scores:read',icon:<TrophyOutlined/>},
 {path:'/course-management',title:'课程管理',permission:'courses:manage',icon:<BookOutlined/>},
 {path:'/student-alerts',title:'心理预警',permission:'student-alerts:read',icon:<AuditOutlined/>},
 {path:'/academic-deadlines',title:'考务管理',permission:'academics:read',icon:<CalendarOutlined/>},
 {path:'/application-progress',title:'申请进度',permission:'applications:read',icon:<FileTextOutlined/>},
 {path:'/leaves',title:'请假审批',permission:'leaves:read',icon:<AuditOutlined/>},
 {path:'/events',title:'活动管理',permission:'events:manage',alternatePermission:'events:check_in',icon:<CalendarOutlined/>},
 {path:'/tickets',title:'投诉工单',permission:'tickets:read',icon:<CustomerServiceOutlined/>},
 {path:'/todos',title:'我的待办',permission:'todos:read',icon:<CheckSquareOutlined/>},
 {path:'/notifications',title:'站内通知',permission:'notifications:read',icon:<BellOutlined/>},
 {path:'/queries',title:'智能查询',permission:'queries:read',icon:<SearchOutlined/>},
 {path:'/commands',title:'业务指令',permission:'commands:execute',icon:<ThunderboltOutlined/>},
 {path:'/settings/website-content',title:'官网内容管理',permission:'website-content:manage',adminOnly:true,icon:<FileTextOutlined/>},
 {path:'/settings/website-accounts',title:'官网账号',permission:'website-accounts:manage',icon:<UserOutlined/>},
 {path:'/settings/users',title:'员工管理',permission:'users:manage',icon:<UserOutlined/>},
 {path:'/settings/roles',title:'角色权限',permission:'roles:manage',icon:<SafetyCertificateOutlined/>},
 {path:'/settings/audit',title:'安全审计',permission:'audit:read',icon:<HistoryOutlined/>},
]

/** 侧栏分组：只决定展示顺序与分组标题，不改变权限判断、路由与页面映射 */
export const navGroups=[
 {label:'工作概览',paths:['/dashboard','/assistant','/todos','/notifications']},
 {label:'客户与业务',paths:['/customers','/visitor-intake','/reporting','/reports','/queries','/commands']},
 {label:'学生事务',paths:['/scores','/course-management','/student-alerts','/academic-deadlines','/application-progress']},
 {label:'组织与协同',paths:['/directory','/guides','/leaves','/events','/tickets']},
 {label:'系统管理',paths:['/settings/website-content','/settings/website-accounts','/settings/users','/settings/roles','/settings/audit']},
]
export const permissionNames:Record<string,string>={
 'website-content:manage':'维护官网栏目与卡片',
 'website-accounts:manage':'管理官网学生身份授权',
 'visitor-intake:read':'查看待认领游客和本人认领资料','visitor-intake:write':'认领游客、记录电话并补录研判',
 'dashboard:read':'工作台','crm:read':'查看本人客户','crm:write':'维护本人客户','reports:read':'查看本人日报','reports:write':'提交本人日报',
 'directory:read':'组织与同事查询','directory:contacts':'查看同事联系方式','guides:read':'查询指南','guides:write':'新增指南',
 'scores:read':'查询授权学生成绩','scores:write':'录入与更正成绩','leaves:read':'查询本人待审批请假','leaves:approve':'审批请假',
 'tickets:read':'查看本人工单','tickets:write':'处理本人工单','todos:read':'查看本人待办','todos:write':'维护本人待办',
 'notifications:read':'查看本人通知','queries:read':'白名单查询','commands:execute':'业务指令','ai:use':'AI助手',
 'users:manage':'管理员工','roles:manage':'配置角色权限','audit:read':'查看安全审计'}


export function workplaceHome(roleCode: string, permittedPaths: string[]) {
 const rolePages: Record<string,string[]> = {
   advisor: ['/visitor-intake','/customers'],
   employee: ['/visitor-intake','/customers'],
   teacher: ['/leaves','/scores','/tickets'],
   team_leader: ['/leaves','/scores','/tickets'],
   manager: ['/tickets','/reports'],
   admin: ['/settings/website-accounts','/settings/users'],
 }
 return rolePages[roleCode]?.find(path => permittedPaths.includes(path)) ?? permittedPaths[0] ?? '/account'
}
