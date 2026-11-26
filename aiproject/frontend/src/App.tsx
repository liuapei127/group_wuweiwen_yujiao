import {lazy, Suspense, useState, type ReactNode} from 'react'
import {Link,Navigate,Route,Routes,useLocation,useNavigate} from 'react-router-dom'
import {Avatar,Button,Drawer,Dropdown,Layout,Menu,Result,Space,Tag,Typography} from 'antd'
import {MenuOutlined,RobotOutlined,UserOutlined,LogoutOutlined,DownOutlined,SearchOutlined,BellOutlined} from '@ant-design/icons'
import {useAuth} from './auth'
import {navigation,navGroups,workplaceHome} from './navigation'
import {ErrorBoundary} from './components/ErrorBoundary'
import {Loading} from './components/shared'
import {Login} from './pages/Login'

const Dashboard = lazy(() => import('./pages/Home').then(m => ({default: m.Dashboard})))
const Account = lazy(() => import('./pages/Home').then(m => ({default: m.Account})))
const Reports = lazy(() => import('./pages/Business').then(m => ({default: m.Reports})))
const Directory = lazy(() => import('./pages/Business').then(m => ({default: m.Directory})))
const Guides = lazy(() => import('./pages/Business').then(m => ({default: m.Guides})))
const Notifications = lazy(() => import('./pages/Business').then(m => ({default: m.Notifications})))
const Queries = lazy(() => import('./pages/Business').then(m => ({default: m.Queries})))
const Commands = lazy(() => import('./pages/Business').then(m => ({default: m.Commands})))
const CustomerDetails = lazy(() => import('./pages/CustomerWorkspace').then(m => ({default: m.CustomerDetails})))
const Customers = lazy(() => import('./pages/CustomerWorkspace').then(m => ({default: m.Customers})))
const Scores = lazy(() => import('./pages/Operations').then(m => ({default: m.Scores})))
const Leaves = lazy(() => import('./pages/Operations').then(m => ({default: m.Leaves})))
const Tickets = lazy(() => import('./pages/Operations').then(m => ({default: m.Tickets})))
const Todos = lazy(() => import('./pages/Operations').then(m => ({default: m.Todos})))
const Users = lazy(() => import('./pages/Administration').then(m => ({default: m.Users})))
const Roles = lazy(() => import('./pages/Administration').then(m => ({default: m.Roles})))
const Audits = lazy(() => import('./pages/Administration').then(m => ({default: m.Audits})))
const Assistant = lazy(() => import('./pages/Assistant').then(m => ({default: m.Assistant})))
const Events = lazy(() => import('./pages/Events').then(m => ({default: m.Events})))
const StaffDeadlines = lazy(() => import('./pages/AcademicDeadlines').then(m => ({default: m.StaffDeadlines})))
const StaffCourses = lazy(() => import('./pages/WebsiteCourses').then(m => ({default: m.StaffCourses})))
const ReportCenter = lazy(() => import('./pages/ReportCenter').then(m => ({default: m.ReportCenter})))
const ReportRuleSettings = lazy(() => import('./pages/ReportRuleSettings').then(m => ({default: m.ReportRuleSettings})))
const WeeklySubmission = lazy(() => import('./pages/WeeklySubmission').then(m => ({default: m.WeeklySubmission})))
const StudentAlerts = lazy(() => import('./pages/StudentAlerts').then(m => ({default: m.StudentAlerts})))
const ApplicationProgress = lazy(() => import('./pages/ApplicationProgress').then(m => ({default: m.ApplicationProgress})))
const VisitorIntake = lazy(() => import('./pages/VisitorIntake').then(m => ({default: m.VisitorIntake})))
const WebsiteContent = lazy(() => import('./pages/WebsiteContent').then(m => ({default: m.WebsiteContent})))
const WebsiteAccounts = lazy(() => import('./pages/WebsiteAccounts').then(m => ({default: m.WebsiteAccounts})))
const ClassManagement = lazy(() => import('./pages/ClassManagement').then(m => ({default: m.ClassManagement})))
const TeacherManagement = lazy(() => import('./pages/TeacherManagement').then(m => ({default: m.TeacherManagement})))
const MyStudents = lazy(() => import('./pages/MyStudents').then(m => ({default: m.MyStudents})))
const TeachingCourses = lazy(() => import('./pages/TeachingCourses').then(m => ({default: m.TeachingCourses})))
const TicketRouting = lazy(() => import('./pages/TicketRouting').then(m => ({default: m.TicketRouting})))

const pages:Record<string,ReactNode>={'/dashboard':<Dashboard/>,'/assistant':<Assistant/>,'/customers':<Customers/>,'/visitor-intake':<VisitorIntake/>,'/reports':<><Reports/><WeeklySubmission/></>,'/reporting':<ReportCenter/>,'/student-alerts':<StudentAlerts/>,'/directory':<Directory/>,'/guides':<Guides/>,'/scores':<Scores/>,'/leaves':<Leaves/>,'/tickets':<Tickets/>,'/events':<Events/>,'/academic-deadlines':<StaffDeadlines/>,'/course-management':<StaffCourses/>,'/class-management':<ClassManagement/>,'/my-students':<MyStudents/>,'/teaching-courses':<TeachingCourses/>,'/ticket-routing':<TicketRouting/>,'/teacher-management':<TeacherManagement/>,'/application-progress':<ApplicationProgress/>,'/todos':<Todos/>,'/notifications':<Notifications/>,'/queries':<Queries/>,'/commands':<Commands/>,'/settings/website-content':<WebsiteContent/>,'/settings/website-accounts':<WebsiteAccounts/>,'/settings/users':<Users/>,'/settings/roles':<Roles/>,'/settings/audit':<Audits/>}

pages['/settings/report-rules']=<ReportRuleSettings/>

export default function App(){
  const {user,loading,can,logout}=useAuth()
  const loc=useLocation()
  const navigate=useNavigate()
  const [drawer,setDrawer]=useState(false)
  if(loading)return <Loading/>
  if(!user)return <Login/>

  const permitted=navigation.filter(n=>(!n.adminOnly||user.role_code==='admin')&&(can(n.permission)||Boolean(n.alternatePermission&&can(n.alternatePermission))||Boolean(n.extraPermissions?.some(can))))
  const permittedPaths=new Set(permitted.map(n=>n.path))
  const first=workplaceHome(user.role_code,permitted.map(item=>item.path))
  const active=navigation.find(n=>n.path===loc.pathname)

  // 按业务域分组展示；权限过滤结果与原逻辑完全一致，空分组自动隐藏
  const items=navGroups
    .map(group=>({type:'group' as const,label:group.label,children:permitted.filter(n=>group.paths.includes(n.path)).map(n=>({key:n.path,icon:n.icon,label:n.title}))}))
    .filter(group=>group.children.length)

  const side=<>
    <Link className="brand sidebar-brand" to={first}>
      <div className="brand-mark">E</div>
      <span>ENT<span className="brand-sub">企业智能工作台</span></span>
    </Link>
    <div className="nav-label">工作空间</div>
    <Menu theme="light" mode="inline" selectedKeys={[loc.pathname]} items={items} onClick={e=>{navigate(e.key);setDrawer(false)}}/>
    <div className="sidebar-foot"><span className="status-dot online"/> 本地联调工作空间</div>
  </>

  return <Layout className="app-shell">
    <Layout.Sider width={248} className="desktop-sider">{side}</Layout.Sider>
    <Drawer placement="left" open={drawer} onClose={()=>setDrawer(false)} size={268} styles={{body:{padding:0,background:'#FFFFFF'}}} className="mobile-menu">{side}</Drawer>
    <Layout className="main-layout">
      <Layout.Header className="app-header">
        <div className="header-left">
          <Button className="mobile-menu-button" type="text" icon={<MenuOutlined/>} onClick={()=>setDrawer(true)}/>
          <span className="header-section">工作空间</span>
          <span className="header-slash">/</span>
          <Typography.Text strong>{active?.title||(loc.pathname==='/account'?'我的账号':'工作台')}</Typography.Text>
        </div>
        <Space size="middle">
          {can('queries:read')&&<Link to="/queries" className="header-tool" title="智能查询"><Button type="text" icon={<SearchOutlined/>} aria-label="智能查询"/></Link>}
          {can('notifications:read')&&<Link to="/notifications" className="header-tool" title="站内通知"><Button type="text" icon={<BellOutlined/>} aria-label="站内通知"/></Link>}
          <span className="header-divider"/>
          {can('ai:use')&&<Link to="/assistant"><Button type="text" icon={<RobotOutlined/>}>AI 助手</Button></Link>}
          <Tag className="role-tag">{user.role_name}</Tag>
          <Dropdown menu={{items:[{key:'account',label:'我的账号',icon:<UserOutlined/>,onClick:()=>navigate('/account')},{key:'logout',label:'退出登录',icon:<LogoutOutlined/>,onClick:()=>void logout()}]}}>
            <Button type="text" className="user-menu">
              <Avatar size="small" style={{background:'#D9EFEA',color:'#0B5F58'}}>{user.real_name.slice(0,1)}</Avatar>
              <span>{user.real_name}</span>
              <DownOutlined/>
            </Button>
          </Dropdown>
        </Space>
      </Layout.Header>
      <Layout.Content className="page-content">
        <ErrorBoundary key={loc.pathname}>
          <Suspense fallback={<Loading/>}>
            <Routes>
              <Route path="/" element={<Navigate to={first} replace/>}/>
              <Route path="/login" element={<Navigate to={first} replace/>}/>
              <Route path="/account" element={<Account/>}/>
              <Route path="/profile-screening" element={<Navigate to="/customers" replace/>}/>
              <Route path="/customers/:id" element={can('crm:read')?<CustomerDetails/>:<Result status="403" title="暂无访问权限"/>}/>
              {navigation.map(n=><Route key={n.path} path={n.path} element={permittedPaths.has(n.path)?pages[n.path]:<Result status="403" title="暂无访问权限" subTitle="你的当前角色尚未获得这项功能权限，请联系管理员。" extra={<Button onClick={()=>navigate(first)}>返回我的工作台</Button>}/>}/>)}
              <Route path="*" element={<Result status="404" title="页面不存在" extra={<Link to={first}><Button>返回工作台</Button></Link>}/>}/>
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </Layout.Content>
      <Layout.Footer className="app-footer">ENT 企业智能工作台 · 以真实接口和授权范围为准</Layout.Footer>
    </Layout>
  </Layout>
}
