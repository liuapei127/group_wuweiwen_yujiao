import {useState} from 'react'
import {Link} from 'react-router-dom'
import {Alert,App,Button,Card,Descriptions,Form,Input,Space,Statistic,Tag,Typography} from 'antd'
import {ArrowRightOutlined,RobotOutlined,TeamOutlined,FileTextOutlined,AuditOutlined,CheckSquareOutlined,CustomerServiceOutlined,BellOutlined,TrophyOutlined} from '@ant-design/icons'
import {useQuery} from '@tanstack/react-query'
import {api,type Row} from '../lib/api'
import {useAuth} from '../auth'
import {ErrorNotice,PageTitle} from '../components/shared'
import {navigation,navGroups,permissionNames} from '../navigation'
const metricNames:Record<string,string>={customers:'本人客户',reports_today:'今日日报',leaves_pending:'待审批请假',todos_open:'未完成待办',tickets_open:'待处理工单',notifications:'站内通知',authorized_students:'授权学生'}
const kpiIcons=[<TeamOutlined/>,<FileTextOutlined/>,<AuditOutlined/>,<CheckSquareOutlined/>,<CustomerServiceOutlined/>,<BellOutlined/>,<TrophyOutlined/>]
export function Dashboard(){
  const {user,can}=useAuth()
  const result=useQuery({queryKey:[user?.id,'portal-context'],queryFn:()=>api('/api/v1/portal/context')})
  const health=useQuery({queryKey:[user?.id,'portal-health'],queryFn:()=>api('/api/v1/portal/health')})
  const features=navigation.filter(n=>(can(n.permission)||Boolean(n.alternatePermission&&can(n.alternatePermission)))&&n.path!=='/dashboard')
  const counters=Object.entries(result.data?.counters||{})
  const groups=navGroups.map(g=>({label:g.label,items:features.filter(n=>g.paths.includes(n.path))})).filter(g=>g.items.length)
  const today=new Intl.DateTimeFormat('zh-CN',{month:'long',day:'numeric',weekday:'long'}).format(new Date())
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
      {counters.map(([k,v],i)=><Card key={k} className="kpi-card">
        <div className="kpi-top"><div className="kpi-icon">{kpiIcons[i%kpiIcons.length]}</div><span className="kpi-label">{metricNames[k]||k}</span></div>
        <Statistic value={Number(v)}/>
        <span className="stat-hint">当前授权范围</span>
      </Card>)}
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
export function Account(){const {user,logout}=useAuth();const {message}=App.useApp();const [form]=Form.useForm();const [busy,setBusy]=useState(false);const [error,setError]=useState<any>();async function change(values:Row){setBusy(true);setError(null);try{await api('/api/v1/auth/password',{method:'POST',body:{old_password:values.old_password,new_password:values.new_password}});void message.success('密码已更新，请重新登录');await logout()}catch(e){setError(e)}finally{setBusy(false)}}return <><PageTitle title="我的账号" description="查看登录身份与授权范围，维护自己的登录密码。"/><div className="two-column"><Card title="员工信息"><Descriptions column={1} items={[{key:'name',label:'姓名',children:user?.real_name},{key:'username',label:'登录账号',children:user?.username},{key:'role',label:'当前角色',children:user?.role_name},{key:'department',label:'部门',children:user?.department||'—'},{key:'contact',label:'联系方式',children:user?.contact_info||'—'},{key:'scope',label:'授权学生数量',children:user?.student_ids.length||0}]}/><Typography.Title level={5}>我的权限</Typography.Title><Space wrap>{user?.permissions.map(p=><Tag key={p}>{permissionNames[p]||p}</Tag>)}</Space></Card><Card title="修改密码"><Alert type="info" showIcon title="修改密码后所有登录会话都会失效，需要重新登录。" style={{marginBottom:20}}/><ErrorNotice error={error}/><Form form={form} layout="vertical" onFinish={v=>void change(v)}><Form.Item name="old_password" label="原密码" rules={[{required:true,message:'请输入原密码'}]}><Input.Password autoComplete="current-password"/></Form.Item><Form.Item name="new_password" label="新密码" rules={[{required:true,min:12,message:'请输入至少12个字符的新密码'}]}><Input.Password autoComplete="new-password"/></Form.Item><Form.Item name="confirm_password" label="确认新密码" dependencies={['new_password']} rules={[{required:true,message:'请再次输入新密码'},({getFieldValue})=>({validator:(_,v)=>!v||v===getFieldValue('new_password')?Promise.resolve():Promise.reject(new Error('两次密码不一致'))})]}><Input.Password autoComplete="new-password"/></Form.Item><Button type="primary" htmlType="submit" loading={busy}>更新密码</Button></Form></Card></div></>}
