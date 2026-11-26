import {useState} from 'react'
import {Link,useNavigate} from 'react-router-dom'
import {Button,Card,Descriptions,Space,Statistic,Tag,Typography} from 'antd'
import {ArrowRightOutlined,RobotOutlined,TeamOutlined,FileTextOutlined,AuditOutlined,CheckSquareOutlined,CustomerServiceOutlined,BellOutlined,TrophyOutlined} from '@ant-design/icons'
import {useQuery} from '@tanstack/react-query'
import {api} from '../lib/api'
import {useAuth} from '../auth'
import {ActionModal,ErrorNotice,PageTitle,type ActionSpec} from '../components/shared'
import {PasswordChangeDialog} from '../components/PasswordChangeDialog'
import {navigation,navGroups,permissionNames} from '../navigation'
const metricNames:Record<string,string>={customers:'本人客户',reports_today:'今日日报',leaves_pending:'待审批请假',todos_open:'未完成待办',tickets_open:'待处理工单',notifications:'站内通知',authorized_students:'授权学生'}
const kpiIcons=[TeamOutlined,FileTextOutlined,AuditOutlined,CheckSquareOutlined,CustomerServiceOutlined,BellOutlined,TrophyOutlined]
export function Dashboard(){
  const {user,can}=useAuth()
  const result=useQuery({queryKey:[user?.id,'portal-context'],queryFn:()=>api('/api/v1/portal/context')})
  const health=useQuery({queryKey:[user?.id,'portal-health'],queryFn:()=>api('/api/v1/portal/health')})
  const features=navigation.filter(n=>(can(n.permission)||Boolean(n.alternatePermission&&can(n.alternatePermission)))&&n.path!=='/dashboard')
  const counters=Object.entries(result.data?.counters||{})
  const groups=navGroups.map(g=>({label:g.label,items:features.filter(n=>g.paths.includes(n.path))})).filter(g=>g.items.length)
  const [today]=useState(()=>new Intl.DateTimeFormat('zh-CN',{month:'long',day:'numeric',weekday:'long'}).format(new Date()))
  return <>
    <div className="workspace-head">
      <div>
        <div className="workspace-eyebrow">工作概览 · {today}</div>
        <Typography.Title level={2}>{user?.real_name}，欢迎回来</Typography.Title>
        <Typography.Paragraph>从你的工作台开始，掌握待办进度，让每一次处理都有记录。</Typography.Paragraph>
        <Space size="small"><Tag className="workspace-tag">{user?.role_name}</Tag><Tag className="workspace-tag">{user?.department||'未填写部门'}</Tag></Space>
      </div>
      {can('ai:use')&&<Link to="/assistant"><Button icon={<RobotOutlined/>} className="workspace-cta">让 AI 协助处理</Button></Link>}
    </div>
    <ErrorNotice error={result.error}/>
    <div className="kpi-grid">
      {counters.map(([k,v],i)=>{const Icon=kpiIcons[i%kpiIcons.length];return <Card key={k} className="kpi-card">
        <div className="kpi-top"><div className="kpi-icon"><Icon/></div><span className="kpi-label">{metricNames[k]||k}</span></div>
        <Statistic value={Number(v)}/>
        <span className="stat-hint">当前授权范围</span>
      </Card>})}
    </div>
    <div className="workspace-grid">
      <div className="workspace-main">
        <div className="section-heading"><Typography.Title level={4}>快捷入口</Typography.Title><Typography.Text type="secondary">根据当前角色与权限展示</Typography.Text></div>
        {groups.map(g=><div className="shortcut-group" key={g.label}>
          <div className="shortcut-group-title">{g.label}</div>
          <div className="shortcut-list">
            {g.items.map(n=><Link key={n.path} to={n.path} className="shortcut-item">
              <span className="shortcut-icon">{n.icon}</span>
              <span className="shortcut-label">{n.title}</span>
              <ArrowRightOutlined className="shortcut-arrow"/>
            </Link>)}
          </div>
        </div>)}
      </div>
      <aside className="workspace-side">
        <Card className="system-card" title="连接与访问状态">
          <div className="status-list">
            <div className="status-row"><span className="status-indicator ok"/><span>后端与数据库</span><b>{health.data?.database==='connected'?'已连接':'检查中'}</b></div>
            <div className="status-row"><span className="status-indicator ok"/><span>身份与角色权限</span><b>已验证</b></div>
            <div className="status-row"><span className={'status-indicator '+(health.data?.ai_configured?'ok':'idle')}/><span>AI 引擎</span><b>{health.data?.ai_configured?'Dify 已配置':'等待配置'}</b></div>
          </div>
          <Typography.Paragraph type="secondary" className="system-note">客户、日报、工单和待办按本人归属访问；成绩按服务端学生授权范围访问。</Typography.Paragraph>
        </Card>
        <Card className="side-tip" title="使用提示">
          <Typography.Paragraph type="secondary">左侧导航按业务域分组；所有写入操作会先核对再提交，结果以服务端返回为准。</Typography.Paragraph>
        </Card>
      </aside>
    </div>
  </>
}
export function Account() {
  const {user,logout,reload} = useAuth()
  const navigate = useNavigate()
  const [changingPassword,setChangingPassword] = useState(false)
  const [profileAction, setProfileAction] = useState<ActionSpec | null>(null)

  return <>
    <PageTitle title="我的账号" description="查看登录身份与授权范围，维护自己的信息和登录密码。"
      extra={<Button onClick={() => setProfileAction({
        title: '维护个人信息', path: '/api/v1/auth/profile', method: 'PATCH',
        initial: {real_name: user?.real_name, contact_info: user?.contact_info},
        fields: [{name: 'real_name', label: '姓名', required: true}, {name: 'contact_info', label: '联系方式'}],
      })}>维护个人信息</Button>}/>
    <div className="two-column">
      <Card title="员工信息">
        <Descriptions column={1} items={[
          {key:'name',label:'姓名',children:user?.real_name},
          {key:'username',label:'登录账号',children:user?.username},
          {key:'role',label:'当前角色',children:user?.role_name},
          {key:'department',label:'部门',children:user?.department||'—'},
          {key:'contact',label:'联系方式',children:user?.contact_info||'—'},
          {key:'scope',label:'授权学生数量',children:user?.student_ids.length||0},
        ]}/>
        <Typography.Title level={5}>我的权限</Typography.Title>
        <Space wrap>{user?.permissions.map(p=><Tag key={p}>{permissionNames[p]||p}</Tag>)}</Space>
      </Card>
      <Card title="账号安全">
        <Button type="primary" onClick={()=>setChangingPassword(true)}>修改密码</Button>
      </Card>
    </div>
    {changingPassword && <PasswordChangeDialog username={user?.username} contact={user?.contact_info}
      submit={passwords=>api('/api/v1/auth/password',{method:'POST',body:passwords})}
      onClose={()=>setChangingPassword(false)}
      onChanged={()=>void logout().catch(()=>undefined).then(()=>navigate('/login',{replace:true}))}/>}
    <ActionModal action={profileAction} onClose={() => setProfileAction(null)} onSuccess={() => void reload()}/>
  </>
}
