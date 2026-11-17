import {useState} from 'react'
import {Alert,App,Button,Card,Checkbox,Empty,Form,Modal,Space,Spin,Table,Tabs,Tag,Typography} from 'antd'
import {PlusOutlined} from '@ant-design/icons'
import {useQuery,useQueryClient} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {api,type Row} from '../lib/api'
import {navigation,navGroups} from '../navigation'
import {ErrorNotice,FormFields,PageTitle} from '../components/shared'

type Permission={code:string;name:string;group:string;system_admin:boolean}

export function Roles(){
  const {user,reload}=useAuth()
  const {message}=App.useApp()
  const cache=useQueryClient()
  const [editing,setEditing]=useState<Row|null>(null)
  const [grants,setGrants]=useState<string[]>([])
  const [form]=Form.useForm()
  const roleCode=Form.useWatch('role_code',form)
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState<unknown>()
  const result=useQuery({queryKey:[user?.id,'roles'],queryFn:()=>api<Row[]>('/api/v1/auth/roles')})
  const catalog=useQuery({queryKey:[user?.id,'permissions'],queryFn:()=>api<Permission[]>('/api/v1/auth/permissions')})
  const permissions=catalog.data||[]
  const isAdmin=(roleCode??editing?.role_code)==='admin'
  const selected=isAdmin?permissions.map(p=>p.code):grants
  const ready=catalog.isSuccess&&!catalog.isFetching&&permissions.length>0
  const groups=Array.from(new Set(permissions.map(p=>p.group)))
  const open=(role:Row)=>{
    setEditing(role);setGrants(role.permissions||[]);setError(undefined)
    form.resetFields();form.setFieldsValue({...role,status:role.status??1})
  }
  function choices(codes:string[]){
    const entries=permissions.filter(p=>codes.includes(p.code))
    return <Checkbox.Group value={selected.filter(code=>codes.includes(code))}
      options={entries.map(p=>({value:p.code,label:p.name,disabled:isAdmin}))}
      onChange={checked=>setGrants([...grants.filter(code=>!codes.includes(code)),...checked as string[]])}/>
  }
  async function save(){
    try{
      const fields=await form.validateFields()
      if(!ready)return
      setBusy(true);setError(undefined)
      await api('/api/v1/auth/roles'+(editing?.id?'/'+editing.id:''),{
        method:editing?.id?'PUT':'POST',body:{...fields,permissions:fields.role_code==='admin'?permissions.map(p=>p.code):grants},
      })
      void message.success('角色权限已保存');setEditing(null)
      await reload();void cache.invalidateQueries()
    }catch(e){setError(e)}finally{setBusy(false)}
  }
  const functionPermissions=<div className="permission-grid">{groups.map(group=><Card size="small" key={group} title={group}>
    {choices(permissions.filter(p=>p.group===group).map(p=>p.code))}
  </Card>)}</div>
  const menuPermissions=<div style={{maxHeight:390,overflow:'auto'}}>{navGroups.map(group=><Card size="small" key={group.label} title={group.label}>
    <Table rowKey="path" size="small" pagination={false} showHeader={false}
      dataSource={navigation.filter(n=>group.paths.includes(n.path))}
      columns={[
        {title:'菜单',width:180,render:(_,item)=><Space orientation="vertical" size={0}>
          <Typography.Text strong>{item.title}</Typography.Text>
          {item.adminOnly&&<Typography.Text type="secondary">仅系统管理员菜单</Typography.Text>}
        </Space>},
        {title:'入口权限',render:(_,item)=>{
          const codes=[item.permission,...(item.alternatePermission?[item.alternatePermission]:[]),...(item.extraPermissions||[])]
          return <Space orientation="vertical" size={4}>
            {choices(codes)}
            {codes.length>1&&<Typography.Text type="secondary">勾选任一项可显示此菜单</Typography.Text>}
          </Space>
        }},
      ]}/>
  </Card>)}</div>
  return <>
    <PageTitle title="角色权限" description="按菜单入口及业务功能分配权限。" extra={<Button type="primary" icon={<PlusOutlined/>} onClick={()=>open({})}>新增角色</Button>}/>
    <ErrorNotice error={result.error}/>
    <Card className="table-card"><Table<Row> rowKey="id" dataSource={result.data||[]} loading={result.isLoading} pagination={false} columns={[
      {title:'角色名称',dataIndex:'role_name'},{title:'编码',dataIndex:'role_code'},{title:'说明',dataIndex:'description'},
      {title:'状态',dataIndex:'status',render:v=><Tag color={v===1?'success':'default'}>{v===1?'启用':'停用'}</Tag>},
      {title:'权限数量',dataIndex:'permissions',render:v=>v?.length||0},
      {title:'操作',render:(_,r)=>r.role_code==='student'?<Typography.Text type="secondary">学生基础角色</Typography.Text>:<Button type="link" onClick={()=>open(r)}>配置权限</Button>},
    ]}/></Card>
    <Modal open={Boolean(editing)} title={editing?.id?'配置角色权限':'新增角色'} onCancel={()=>setEditing(null)} onOk={()=>void save()}
      confirmLoading={busy} okButtonProps={{disabled:!ready}} okText="保存权限" cancelText="取消" width={960} destroyOnHidden>
      <ErrorNotice error={error}/><ErrorNotice error={catalog.error}/>
      <Form form={form} layout="vertical"><FormFields fields={[
        {name:'role_code',label:'角色编码',required:true,disabled:Boolean(editing?.id),help:'小写字母开头，使用小写字母、数字或下划线；创建后不可改。'},
        {name:'role_name',label:'角色名称',required:true},{name:'description',label:'角色说明'},
        {name:'status',label:'状态',kind:'select',required:true,options:[{value:1,label:'启用'},{value:0,label:'停用'}]},
      ]}/></Form>
      {isAdmin&&<Alert type="info" showIcon title="管理员固定拥有全部功能权限，已全部勾选，无需逐项配置；新增功能权限也会自动生效。"/>}
      <Typography.Paragraph type="secondary">菜单入口权限与功能权限共用同一份授权。共用权限的菜单会同步勾选；新增、编辑、审批等操作请在“功能权限”中配置。数据访问仍受本人、部门和学生授权范围限制。</Typography.Paragraph>
      <div className="permission-toolbar"><Typography.Text strong>功能权限 · 共 {permissions.length} 项 · 已选 {selected.length} 项</Typography.Text><Space>
        <Button size="small" disabled={!ready||isAdmin} onClick={()=>setGrants(permissions.map(p=>p.code))}>全选</Button>
        <Button size="small" disabled={!ready||isAdmin} onClick={()=>setGrants([])}>清空</Button>
      </Space></div>
      {(catalog.isError||(catalog.isSuccess&&!permissions.length))&&<Button onClick={()=>void catalog.refetch()}>重新加载权限目录</Button>}
      {catalog.isPending?<Spin tip="正在加载权限目录"><div style={{minHeight:120}}/></Spin>:catalog.isSuccess&&!permissions.length?<Empty description="权限目录为空，请重新加载后再保存"/>:catalog.isSuccess&&<Tabs defaultActiveKey="menus" items={[
        {key:'menus',label:'菜单权限（'+navigation.length+'）',children:menuPermissions},
        {key:'functions',label:'功能权限',children:functionPermissions},
      ]}/>}
    </Modal>
  </>
}
