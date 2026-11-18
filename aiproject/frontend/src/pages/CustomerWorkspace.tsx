import {useEffect, useState} from 'react'
import {Link, useNavigate, useParams} from 'react-router-dom'
import {Alert, App, Button, Card, Input, Select, Space, Table, Tag, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ActionModal, ErrorNotice, PageTitle, Status, Value, options, type ActionSpec} from '../components/shared'
import {CustomerPortraitInput, CustomerProfilePanel, customerValue, useCustomerEditor, usePortraitUpdates, type CustomerProfile, type Request} from '../components/CustomerProfilePanel'
import {CustomerImportedMaterials, type ImportedMaterial} from '../components/CustomerImportedMaterials'
import {api, query} from '../lib/api'
import {CustomerVisitorMaterials, screeningStatuses} from './VisitorIntake'
import './customer-workspace.css'

const leads = '/api/v1/consultant/leads'
const leadStates = ['new', 'contacting', 'qualified', 'signed', 'lost']
const missingLabels: Record<string, string> = {project: '意向项目', age: '年龄', education: '学历类别', education_stage: '在读或毕业状态'}
const followTypes: Record<string, string> = {phone: '电话', wechat: '微信', meeting: '面谈', email: '邮件', other: '其他'}
const request: Request = <T,>(path: string, method?: string, body?: unknown, onText?: (text: string) => void) =>
  api<T>(path, {method, body, onText, timeout: 65000})

type Lead = {id: number; customer_name: string; status: string}
const customerPath = (row: Lead) => '/customers/' + row.id

type FollowUp = {id: number; follow_type: string | null; content: string; next_plan: string | null; create_time: string}
type Detail = {lead: Lead; follow_ups: FollowUp[]}
type Missing = {ready: boolean; missing_fields: string[]}
type Screening = {
  id: number; version?: number; stale: boolean; result?: {status: string; findings: string[]}
  input_snapshot?: Record<string, unknown>[]
  ai?: {state: string; message?: string; recommendation?: string; talk_track?: string}
}
type StaffProfile = CustomerProfile & {visitor_id?: number | null; readiness: Missing; screening: Screening | null; imports?: ImportedMaterial[]}

export function Customers() {
  const {user} = useAuth()
  const navigate = useNavigate()
  const [keyword, setKeyword] = useState('')
  const [status, setStatus] = useState<string>()
  const [page, setPage] = useState(1)
  const list = useQuery({
    queryKey: [user?.id, 'crm-customers', keyword, status, page],
    queryFn: () => api<{items: Lead[]; total: number}>(
      '/api/v1/consultant/customers' + query({keyword, status, page, page_size: 20})),
    refetchOnWindowFocus: true,
  })
  return <>
    <PageTitle title="客户管理" description="查看我跟进的客户和当前状态。"/>
    <Card>
      <Space wrap style={{marginBottom: 16}}>
        <Input.Search aria-label="搜索客户" placeholder="搜索姓名或昵称" allowClear
          onSearch={text => {setKeyword(text.trim()); setPage(1)}}/>
        <Select aria-label="客户状态筛选" placeholder="全部状态" allowClear options={options(leadStates)}
          onChange={value => {setStatus(value); setPage(1)}} style={{width: 160}}/>
      </Space>
      <ErrorNotice error={list.error}/>
      <Table<Lead> rowKey="id" loading={list.isFetching} dataSource={list.data?.items ?? []}
        locale={{emptyText: '暂无跟进客户'}} pagination={{
          total: list.data?.total ?? 0, current: page, pageSize: 20, showSizeChanger: false, onChange: setPage,
        }} onRow={row => ({onClick: () => void navigate(customerPath(row)), className: 'customer-list-row'})}
        columns={[
          {title: '客户姓名', render: (_, row) => <Link to={customerPath(row)} onClick={event => event.stopPropagation()}>{row.customer_name}</Link>},
          {title: '跟进状态', dataIndex: 'status', render: value => <Status value={value}/>},
        ]}/>
    </Card>
  </>
}

export function CustomerDetails() {
  const {id} = useParams()
  const {user} = useAuth()
  return <CustomerDetail key={id} id={String(id)} userId={user?.id}/>
}

function CustomerDetail({id, userId}: {id: string; userId?: number}) {
  const {can} = useAuth()
  const {message} = App.useApp()
  const cache = useQueryClient()
  const [action, setAction] = useState<ActionSpec | null>(null)
  const [requested, setRequested] = useState(false)
  const [editCheck, setEditCheck] = useState<object>()
  const base = leads + '/' + id
  const profileUrl = base + '/profile'
  const detailKey = [userId, 'crm-detail', id]
  const profileKey = [userId, 'crm-profile', id]
  const detail = useQuery({queryKey: detailKey, queryFn: () => api<Detail>(base), refetchOnWindowFocus: true})
  const profile = useQuery({
    queryKey: profileKey, queryFn: () => api<StaffProfile>(profileUrl),
    staleTime: 0, refetchOnWindowFocus: true, refetchOnReconnect: true, refetchInterval: 15000,
  })
  usePortraitUpdates(request, profileUrl, profile.data?.version, profile.refetch)
  function refresh() {
    void cache.invalidateQueries({queryKey: detailKey})
    void cache.invalidateQueries({queryKey: profileKey})
    void cache.invalidateQueries({queryKey: [userId, 'crm-customers']})
  }
  const editor = useCustomerEditor(profile.data, request, profileUrl, refresh)
  const changes = editor.draft?.changes
  useEffect(() => {
    setEditCheck(undefined)
    if (!changes) return
    const timer = window.setTimeout(() => setEditCheck(changes), 230)
    return () => window.clearTimeout(timer)
  }, [changes])
  const check = useQuery({
    queryKey: [userId, 'crm-readiness', id, editCheck, profile.data?.version],
    enabled: !!changes && !!editCheck,
    queryFn: () => request<Missing>(base + '/readiness', 'POST', editCheck),
  })
  const run = useMutation({
    mutationFn: async () => {
      if (!profile.data) return
      setRequested(true)
      const readiness = await request<Missing>(base + '/readiness', 'POST', changes ?? {})
      if (!readiness.ready) {
        void message.warning('资料不全，请补充后再研判')
        return readiness
      }
      let version = profile.data.version
      if (editor.draft && changes && Object.keys(changes).length) {
        const saved = await editor.save.mutateAsync(editor.draft)
        version = saved.version
      }
      return request<Missing & {screening?: Screening}>(base + '/screening', 'POST', {expected_version: version})
    },
    onSuccess: refresh,
  })

  const lead = detail.data?.lead
  const screened = profile.data?.screening
  const current = changes && editCheck === changes ? check.data : profile.data?.readiness
  const ready = current?.ready && (!changes || editCheck === changes)
  const missing = current?.missing_fields ?? []
  const write = can('crm:write')
  const updateStatus = () => setAction({
    title: '更新客户状态', method: 'PATCH', path: base + '/status',
    initial: {status: lead?.status},
    fields: [
      {name: 'status', label: '目标状态', kind: 'select', required: true, options: options(leadStates),
        help: '签约时按合同约定收取项目费用。'},
      {name: 'lost_reason', label: '流失原因', kind: 'textarea'},
    ],
  })
  const follow = () => setAction({
    title: '新增跟进', method: 'POST', path: base + '/follow-ups',
    fields: [
      {name: 'follow_type', label: '沟通方式', kind: 'select', options: Object.entries(followTypes).map(([value, label]) => ({value, label}))},
      {name: 'content', label: '跟进内容', kind: 'textarea', required: true},
      {name: 'next_plan', label: '下一步计划', kind: 'textarea'},
    ],
  })
  return <>
    <Link to="/customers" className="customer-return">← 返回客户列表</Link>
    <PageTitle title={profile.data?.customer_name || lead?.customer_name || '客户详情'} description="客户详情"
      extra={lead && <Space><Status value={lead.status}/>{write && <Button onClick={updateStatus}>修改状态</Button>}</Space>}/>
    <ErrorNotice error={detail.error || profile.error}/>
    {profile.data && <div className="customer-detail-grid">
      <Space orientation="vertical" size="middle" style={{width: '100%'}}>
        <CustomerProfilePanel profile={profile.data} request={request} endpoint={profileUrl} importEndpoint={base} editor={editor} canWrite={write} onSaved={refresh}/>
        <CustomerImportedMaterials imports={profile.data.imports} request={request} endpoint={base} scope={userId}/>
        {profile.data.visitor_id != null && can('visitor-intake:read') &&
          <CustomerVisitorMaterials key={profile.data.visitor_id} visitorId={profile.data.visitor_id} userId={userId}
            importEndpoint={base} onImported={refresh}/>}
        <Card title="跟进记录" extra={write && <Button type="link" onClick={follow}>新增跟进</Button>}>
          <Table<FollowUp> size="small" rowKey="id" pagination={false} locale={{emptyText: '暂无跟进记录'}}
            dataSource={detail.data?.follow_ups ?? []} columns={[
              {title: '方式', render: (_, row) => followTypes[row.follow_type || ''] || '—'},
              {title: '沟通内容', dataIndex: 'content', render: value => <Typography.Text style={{whiteSpace: 'pre-wrap'}}>{value}</Typography.Text>},
              {title: '下一步', dataIndex: 'next_plan', render: value => value || '—'},
              {title: '时间', dataIndex: 'create_time', render: value => <Value value={value}/>},
            ]}/>
        </Card>
      </Space>
      <Card className="customer-screening" title="客户研判"
        extra={<Tag color={ready ? 'success' : 'warning'}>{ready ? '资料齐全' : '待补充'}</Tag>}>
        <Space orientation="vertical" size="middle" style={{width: '100%'}}>
          <Typography.Text>当前项目　{customerValue('intended_project', changes && 'intended_project' in changes ? changes.intended_project : profile.data.intended_project)}</Typography.Text>
          {!!missing.length && <Alert type="warning" showIcon title={requested ? '信息不全，暂不能研判' : '还需补充资料'}
            description={missing.map(field => missingLabels[field] || field).join('、')}/>}
          <ErrorNotice error={run.error || check.error}/>
          {screened?.result && <div className="customer-screening-result">
            {screened.stale && <Alert type="info" title="资料已更新，请重新研判"/>}
            <Tag color={screened.result.status === 'potential_match' ? 'success' : 'warning'}>
              {screeningStatuses[screened.result.status] || screened.result.status}
            </Tag>
            {screened.result.findings.map(text => <Typography.Paragraph key={text}>{text}</Typography.Paragraph>)}
            {screened.ai?.state === 'ready' && <>
              <Typography.Text strong>跟进建议</Typography.Text>
              <Typography.Paragraph>{screened.ai.recommendation}</Typography.Paragraph>
              {!!screened.ai.talk_track && <><Typography.Text strong>沟通话术</Typography.Text>
                <Typography.Paragraph>{screened.ai.talk_track}</Typography.Paragraph></>}
            </>}
            {screened.ai?.state === 'unavailable' && <Alert type="warning" title={screened.ai.message || 'AI 建议暂不可用'}/>}
            {screened.ai?.state === 'pending' && <Typography.Text type="secondary">AI 建议生成中</Typography.Text>}
          </div>}
          {write && <Button block type={ready ? 'primary' : 'default'} aria-busy={run.isPending}
            disabled={editor.save.isPending || run.isPending} className={ready ? undefined : 'customer-screening-muted'}
            onClick={() => run.mutate()}>{run.isPending ? '研判中…' : screened ? '重新研判' : '研判'}</Button>}
        </Space>
      </Card>
    </div>}
    {profile.data && <CustomerPortraitInput profile={profile.data} snapshot={screened?.input_snapshot} snapshotVersion={screened?.version}/>}
    <ActionModal action={action} onClose={() => setAction(null)} onSuccess={refresh}/>
  </>
}

const publicProfileUrl = '/api/v1/visitors/customer-profile'
const publicProfileRead = publicProfileUrl + '?include_pending=true'
type WebsiteProfile = CustomerProfile & {imports?: ImportedMaterial[]}

export function WebsiteCustomerProfile({request, token, back}: {request: Request; token: string; back: () => void}) {
  const cache = useQueryClient()
  const key = ['visitor', 'crm-profile', token]
  const profile = useQuery({
    queryKey: key,
    queryFn: async () => {
      try {
        return await request<WebsiteProfile>(publicProfileRead)
      } catch (error) {
        // The profile endpoint reports an account without a linked customer as 409.
        if (error instanceof Error && 'status' in error && error.status === 409) return null
        throw error
      }
    },
    refetchOnWindowFocus: true, refetchOnReconnect: true,
    refetchInterval: state => state.state.data === null ? 2000 : 15000, staleTime: 0,
  })
  usePortraitUpdates(request, publicProfileRead, profile.data?.version, profile.refetch)
  const refresh = () => {
    void cache.invalidateQueries({queryKey: key})
    void cache.invalidateQueries({queryKey: ['visitor', 'profile', token]})
  }
  const editor = useCustomerEditor(profile.data ?? undefined, request, publicProfileUrl, refresh)
  return <section className="visitor-section customer-website-profile">
    <PageTitle title="我的资料" description="查看和维护与本人账号关联的资料。"
      extra={<Button onClick={back}>返回服务</Button>}/>
    <ErrorNotice error={profile.error}/>
    {(profile.data === null || profile.data?.pending_customer) && <Alert type="info" showIcon title="顾问尚未建立你的客户资料"
      description="你可以向客服补充留学情况或提交材料。顾问建立客户资料后，可在这里编辑。"/>}
    {profile.data && <Space orientation="vertical" size="middle" style={{width: '100%'}}>
      <CustomerProfilePanel profile={profile.data} request={request} endpoint={publicProfileUrl} editor={editor} canWrite={!profile.data.pending_customer} onSaved={refresh}/>
      <CustomerImportedMaterials imports={profile.data.imports} request={request} endpoint={publicProfileUrl} scope={token} token={token}/>
    </Space>}
  </section>
}
