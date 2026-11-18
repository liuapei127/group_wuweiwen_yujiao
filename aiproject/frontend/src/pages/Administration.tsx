import {useState} from 'react'
import {Button,Card,Input,Space,Table,Tag} from 'antd'
import {PlusOutlined,ReloadOutlined} from '@ant-design/icons'
import {useQuery,useQueryClient} from '@tanstack/react-query'
import {api,query,type Row} from '../lib/api'
import {mobileNumberMessage,mobileNumberPattern} from '../lib/mobile'
import {useAuth} from '../auth'
import {MembershipEditor} from './Membership'
import {PasswordResetDialog} from '../components/PasswordResetDialog'
import {ActionModal,DetailDrawer,ErrorNotice,PageTitle,Status,options,type ActionSpec,type Field} from '../components/shared'
export function Users(){const {user,reload,can}=useAuth();const [membershipId,setMembershipId]=useState<number>();const [passwordTarget,setPasswordTarget]=useState<{id:number;username:string}>();const cache=useQueryClient();const [keyword,setKeyword]=useState('');const [page,setPage]=useState(1);const [action,setAction]=useState<ActionSpec|null>(null);const result=useQuery({queryKey:[user?.id,'admin-users',keyword,page],queryFn:()=>api('/api/v1/auth/users'+query({keyword,page,page_size:20}))});const students=useQuery({queryKey:[user?.id,'admin-students'],queryFn:()=>api<Row[]>('/api/v1/auth/students')});const roleOptions=(result.data?.roles||[]).filter((r:Row)=>r.role_code!=='student'&&r.status===1).map((r:Row)=>({value:r.id,label:r.role_name}));const baseFields:Field[]=[{name:'real_name',label:'员工姓名',required:true},{name:'role_id',label:'角色',kind:'select',required:true,options:roleOptions},{name:'department',label:'部门'},{name:'contact_info',label:'联系方式'},{name:'status',label:'账号状态',kind:'select',initial:'normal',required:true,options:options(['normal','disabled'])}];return <><PageTitle title="员工管理" description="分配角色、管理账号状态、重置密码和配置学生授权。" extra={<><Input.Search placeholder="员工姓名、手机号或账号" allowClear onSearch={v=>{setKeyword(v);setPage(1)}} style={{width:240}}/><Button icon={<ReloadOutlined/>} onClick={()=>void result.refetch()}>刷新</Button><Button type="primary" icon={<PlusOutlined/>} onClick={()=>setAction({title:'新增员工',method:'POST',path:'/api/v1/auth/users',fields:[{name:'username',label:'手机号',required:true,pattern:mobileNumberPattern,help:mobileNumberMessage+'，初始密码为手机号后 6 位。'},...baseFields.filter(f=>f.name!=='contact_info')],successText:'员工已创建，初始密码为手机号后 6 位'})}>新增员工</Button></>}/><ErrorNotice error={result.error}/><Card className="table-card"><Table<Row> rowKey="id" loading={result.isFetching} dataSource={result.data?.items||[]} pagination={{current:page,pageSize:20,total:result.data?.total||0,onChange:setPage,showSizeChanger:false}} scroll={{x:'max-content'}} columns={[{title:'姓名',dataIndex:'real_name',fixed:'left'},{title:'账号',dataIndex:'username'},{title:'角色',dataIndex:'role_name',render:v=><Tag color="blue">{v||'未分配'}</Tag>},{title:'部门',dataIndex:'department'},{title:'状态',dataIndex:'status',render:v=><Status value={v}/>},{title:'操作',key:'ops',width:290,render:(_,r)=><Space wrap><Button type="link" onClick={()=>setAction({title:'编辑员工',method:'PATCH',path:'/api/v1/auth/users/'+r.id,fields:baseFields,initial:r})}>编辑</Button><Button type="link" onClick={()=>setAction({title:'配置学生授权',method:'PUT',path:'/api/v1/auth/users/'+r.id+'/student-scope',initial:{student_ids:r.student_ids||[]},fields:[{name:'student_ids',label:'额外授权学生',kind:'multi',options:(students.data||[]).map(s=>({value:s.id,label:s.real_name+' · '+(s.student_no||s.id)})),help:'已有班主任分班关系会自动生效；此处配置额外学生范围。'}]})}>学生授权</Button>{can('organizations:manage')&&<Button type="link" onClick={()=>setMembershipId(r.id)}>组织关系</Button>}<Button type="link" onClick={()=>setPasswordTarget({id:r.id,username:r.username})}>重置密码</Button></Space>} ]}/></Card><ActionModal action={action} onClose={()=>setAction(null)} onSuccess={()=>{void reload();void cache.invalidateQueries()}}/>
  {passwordTarget && <PasswordResetDialog accountType="员工" username={passwordTarget.username}
    path={'/api/v1/auth/users/'+passwordTarget.id+'/password'} onClose={()=>setPasswordTarget(undefined)}
    onSuccess={()=>{if(passwordTarget.id===user?.id) void reload()}}/>}
  {membershipId&&<MembershipEditor userId={membershipId} close={()=>setMembershipId(undefined)}/>}</>}
export {Roles} from './RolePermissions'
export function Audits(){
  const {user}=useAuth()
  const [detail,setDetail]=useState<Row|null>(null)
  const result=useQuery({queryKey:[user?.id,'audit'],queryFn:()=>api<Row[]>('/api/v1/auth/audit?limit=200')})
  const names:Record<string,string>={login:'登录',logout:'退出登录',password_change:'修改本人密码',password_reset:'管理员重置员工密码',website_password_reset:'管理员重置官网密码',website_password_change:'官网用户修改本人密码',user_create:'新增员工',user_update:'修改员工',student_scope_update:'调整学生授权',role_save:'保存角色权限'}
  const detailData=detail?{
    id:detail.id,
    create_time:detail.create_time,
    actor_id:detail.actor_id,
    action:names[detail.action]||detail.action,
    target:detail.target,
    details:detail.details&&Object.keys(detail.details).length?detail.details:'无额外操作详情',
  }:null
  return <>
    <PageTitle title="安全审计" description="核对登录、账号维护与权限变更，不记录密码和访问令牌。" extra={<Button onClick={()=>void result.refetch()} icon={<ReloadOutlined/>}>刷新</Button>}/>
    <ErrorNotice error={result.error}/>
    <Card className="table-card"><Table<Row> rowKey="id" loading={result.isFetching} dataSource={result.data||[]} columns={[
      {title:'时间（UTC）',dataIndex:'create_time'},
      {title:'操作者编号',dataIndex:'actor_id'},
      {title:'操作',dataIndex:'action',render:v=>names[v]||v},
      {title:'目标',dataIndex:'target'},
      {title:'详情',render:(_,r)=><Button type="link" onClick={()=>setDetail(r)}>查看</Button>},
    ]}/></Card>
    <DetailDrawer title="审计详情" data={detailData} labels={{id:'审计编号',create_time:'时间（UTC）',actor_id:'操作者编号',action:'操作类型',target:'操作目标',details:'附加信息'}} onClose={()=>setDetail(null)}/>
  </>
}
