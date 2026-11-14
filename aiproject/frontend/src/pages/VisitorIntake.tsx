import {useRef, useState} from 'react'
import {Link} from 'react-router-dom'
import {Alert, App, Button, Card, Descriptions, Drawer, Empty, Form, Input, Modal, Select, Space, Table, Tabs, Tag, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ActionModal, ErrorNotice, FormFields, PageTitle, type ActionSpec, type Field} from '../components/shared'
import {api, download, query} from '../lib/api'

type Visitor = {visitor_id: number; registered_at: string}
type AssignedVisitor = Visitor & {
  name: string; contact: string; claimed_at: string; last_contact_at: string | null; manual_source_id: number | null; crm_lead_id?: number | null
}
type Call = {id: number; advisor_id: number; notes: string; recorded_at: string}
type Material = {source_id: number; file_name: string | null; submitted_at: string; status: string}
type ScreeningInput = {
  project?: string | null; age?: number | null; education?: string | null; education_stage?: string | null
}
type ScreeningResult = {status: string; missing_fields: string[]; findings: string[]}
type SourceDetails = {
  source_id: number; raw_content: string | null; file_name: string | null
  screening_input: ScreeningInput | null; screening: ScreeningResult | null
}

const endpoint = '/api/v1/consultant/visitor-intake'
const pageSize = 20
const fieldLabels: Record<string, string> = {project: '意向项目', age: '年龄', education: '学历类别', education_stage: '在读或毕业状态'}
const materialStatuses: Record<string, string> = {received: '已收到', needs_information: '待补充', reviewed: '已研判'}
const screeningStatuses: Record<string, string> = {
  needs_information: '待补充', needs_review: '待人工复核', potential_match: '初筛符合', not_matched: '初筛不符合',
}
const choices = (options: Record<string, string>) => Object.entries(options).map(([value, label]) => ({value, label}))
const screeningFields: Field[] = [
  {name: 'project', label: fieldLabels.project, kind: 'select', options: choices({
    sg_junior: '新加坡初中升学', sg_senior: '新加坡高中或同等学历升学', sg_hospitality: '新加坡酒店就业班',
    sg_aviation: '新加坡航空就业班', sg_top_up: '新加坡专升本', sg_masters: '新加坡本升硕', de_vocational: '德国双元制',
  })},
  {name: 'age', label: fieldLabels.age, kind: 'number'},
  {name: 'education', label: fieldLabels.education, kind: 'select', options: choices({
    junior_secondary: '初中', senior_secondary: '高中', vocational_secondary: '中职或同等学历',
    college: '大专', bachelor: '本科', postgraduate: '研究生', other: '其他',
  })},
  {name: 'education_stage', label: fieldLabels.education_stage, kind: 'select', options: choices({
    enrolled: '在读', senior_year_two: '高二在读', graduated: '已毕业',
  })},
]

function beijingTime(value: string) {
  const utc = value.endsWith('Z') || /[+-]\d{2}:\d{2}$/.test(value) ? value : value + 'Z'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).format(new Date(utc))
}

export function VisitorIntake() {
  const {user, can} = useAuth()
  const {message} = App.useApp()
  const cache = useQueryClient()
  const [tab, setTab] = useState('pending')
  const [after, setAfter] = useState(0)
  const [selected, select] = useState<AssignedVisitor>()
  const [claiming, setClaiming] = useState<Visitor>()
  const access = can('visitor-intake:write')
  const scope = [user?.id, 'visitor-intake']
  const pending = useQuery({
    queryKey: [...scope, 'pending', after], enabled: tab === 'pending',
    queryFn: () => api<Visitor[]>(endpoint + '/pending' + query({after_id: after, limit: pageSize})),
  })
  const assigned = useQuery({
    queryKey: [...scope, 'assigned', after], enabled: tab === 'assigned',
    queryFn: () => api<AssignedVisitor[]>(endpoint + '/assigned' + query({after_id: after, limit: pageSize})),
  })
  const list = tab === 'pending' ? pending : assigned
  const claim = useMutation({
    mutationFn: (visitor: Visitor) => api<AssignedVisitor>(endpoint + '/' + visitor.visitor_id + '/claim', {method: 'POST'}),
    onSuccess: visitor => {
      setClaiming(undefined)
      setAfter(0)
      setTab('assigned')
      select(visitor)
      void cache.invalidateQueries({queryKey: scope})
      void message.success('已认领游客')
    },
    onError: () => void pending.refetch(),
  })

  function openClaim(visitor: Visitor) {
    claim.reset()
    setClaiming(visitor)
  }

  return <>
    <PageTitle title="游客跟进" description="认领注册游客，记录通话后补录资料并查看初筛结果。"
      extra={tab !== "advisor" && <Button onClick={() => void list.refetch()}>刷新</Button>}/>
    <Card>
      <Tabs activeKey={tab} onChange={key => {setAfter(0); setTab(key)}} items={[
        ...(can('crm:read') ? [{key: 'advisor', label: '顾问资料', children: <AdvisorMaterials canWrite={can('crm:write')}/>}]: []),
        {key: 'pending', label: '待认领', children: <>
          <ErrorNotice error={pending.error}/>
          <Table rowKey="visitor_id" dataSource={pending.data || []} loading={pending.isFetching}
            pagination={false} locale={{emptyText: '暂无待认领游客'}} columns={[
              {title: '游客编号', dataIndex: 'visitor_id'},
              {title: '注册时间（北京时间）', dataIndex: 'registered_at', render: beijingTime},
              ...(access ? [{title: '操作', render: (_: unknown, row: Visitor) =>
                <Button type="link" onClick={() => openClaim(row)}>认领</Button>}] : []),
            ]}/>
        </>},
        {key: 'assigned', label: '我已认领', children: <>
          <ErrorNotice error={assigned.error}/>
          <Table rowKey="visitor_id" dataSource={assigned.data || []} loading={assigned.isFetching}
            pagination={false} scroll={{x: 630}} locale={{emptyText: '暂无已认领游客'}} columns={[
              {title: '游客编号', dataIndex: 'visitor_id'},
              {title: '姓名', dataIndex: 'name'},
              {title: '联系方式', dataIndex: 'contact'},
              {title: '最近联系（北京时间）', dataIndex: 'last_contact_at',
                render: value => value ? beijingTime(value) : <Tag>待联系</Tag>},
              {title: '操作', render: (_, row) => <Button type="link" onClick={() => select(row)}>查看跟进</Button>},
            ]}/>
        </>},
      ]}/>
      <Space>
        <Button disabled={!after || list.isFetching} onClick={() => setAfter(0)}>返回首批</Button>
        <Button disabled={list.data?.length !== pageSize || list.isFetching}
          onClick={() => setAfter(list.data?.at(-1)?.visitor_id ?? after)}>查看更多</Button>
      </Space>
    </Card>
    <Modal title="认领游客" open={!!claiming} onCancel={() => setClaiming(undefined)} closable={!claim.isPending}
      cancelButtonProps={{disabled: claim.isPending}} mask={{closable: !claim.isPending}}
      onOk={() => {if (claiming) claim.mutate(claiming)}} confirmLoading={claim.isPending}
      okText="确认认领">
      <ErrorNotice error={claim.error}/>
      <p>认领后，游客 {claiming?.visitor_id} 会进入你的跟进名单。</p>
    </Modal>
    <Drawer title={selected ? selected.name + ' · 跟进记录' : '跟进记录'} open={!!selected}
      onClose={() => select(undefined)} size="large">
      {selected && <IntakeDetail key={selected.visitor_id} visitor={selected} canWrite={access} scope={scope}
        onUpdate={update => select(current => current?.visitor_id === selected.visitor_id ? {...current, ...update} : current)}/>}
    </Drawer>
  </>
}

function IntakeDetail({visitor, canWrite, scope, onUpdate}: {
  visitor: AssignedVisitor; canWrite: boolean; scope: (string | number | undefined)[]
  onUpdate: (update: Partial<AssignedVisitor>) => void
}) {
  const base = endpoint + '/' + visitor.visitor_id
  const cache = useQueryClient()
  const {message} = App.useApp()
  const {can} = useAuth()
  const [leadAction, setLeadAction] = useState<ActionSpec | null>(null)
  const [beforeCall, setBeforeCall] = useState<number>()
  const [beforeMaterial, setBeforeMaterial] = useState<number>()
  const [target, setTarget] = useState<number | 'manual'>('manual')
  const [callForm] = Form.useForm<{notes: string}>()
  const callIds = useRef(new Map<string, string>())
  const calls = useQuery({
    queryKey: [...scope, visitor.visitor_id, 'calls', beforeCall],
    queryFn: () => api<Call[]>(base + '/calls' + query({before_id: beforeCall, limit: pageSize})),
  })
  const materials = useQuery({
    queryKey: [...scope, visitor.visitor_id, 'materials', beforeMaterial],
    queryFn: () => api<Material[]>(base + '/materials' + query({before_id: beforeMaterial, limit: pageSize})),
  })
  const sourcePath = target === 'manual' ? base + '/screening' : base + '/materials/' + target
  const detailsKey = [...scope, visitor.visitor_id, 'details', target]
  const details = useQuery({
    queryKey: detailsKey,
    queryFn: () => api<SourceDetails>(sourcePath),
    enabled: target !== 'manual' || visitor.manual_source_id !== null,
  })
  const difyPreview = useMutation({
    mutationFn: (sourceId: number) => api<{match_result: string; match_reason: string}>(
      base + '/materials/' + sourceId + '/dify-preview', {method: 'POST'}),
  })
  const addCall = useMutation({
    mutationFn: (notes: string) => {
      const text = notes.trim()
      const requestId = callIds.current.get(text) || crypto.randomUUID()
      callIds.current.set(text, requestId)
      return api<Call>(base + '/calls', {method: 'POST', body: {request_id: requestId, notes: text}})
    },
    onSuccess: (record, notes) => {
      callIds.current.delete(notes.trim())
      onUpdate({last_contact_at: record.recorded_at})
      callForm.resetFields()
      setBeforeCall(undefined)
      void cache.invalidateQueries({queryKey: [...scope, visitor.visitor_id, 'calls']})
      void cache.invalidateQueries({queryKey: [...scope, 'assigned']})
      void message.success('通话记录已保存')
    },
  })
  const attachment = useMutation({
    mutationFn: (material: Material) =>
      download(base + '/materials/' + material.source_id + '/attachment', material.file_name || '材料附件'),
    onError: error => {void message.error(error.message)},
  })
  const targetOptions = [
    {label: '顾问独立补录', value: 'manual' as const},
    ...(materials.data || []).map(row => ({label: (row.file_name || '文字资料') + ' · ' + row.source_id, value: row.source_id})),
  ]
  if (target !== 'manual' && !targetOptions.some(item => item.value === target)) {
    targetOptions.push({label: '资料 ' + target, value: target})
  }
  return <Space orientation="vertical" size="large" style={{width: '100%'}}>
    <Descriptions column={1} size="small" items={[
      {key: 'contact', label: '联系方式', children: visitor.contact},
      {key: 'last', label: '最近联系（北京时间）', children: visitor.last_contact_at ? beijingTime(visitor.last_contact_at) : '待联系'},
    ]}/>
    <Card title="通话记录">
      {canWrite && <Form form={callForm} layout="vertical" onFinish={value => addCall.mutate(value.notes)}>
        <Form.Item label="沟通内容" name="notes" rules={[{required: true, whitespace: true}]}>
          <Input.TextArea rows={3} maxLength={10000} disabled={addCall.isPending}/>
        </Form.Item>
        <ErrorNotice error={addCall.error}/>
        <Button type="primary" htmlType="submit" loading={addCall.isPending}>保存通话记录</Button>
      </Form>}
      <ErrorNotice error={calls.error}/>
      <Table size="small" rowKey="id" loading={calls.isFetching} pagination={false} dataSource={calls.data || []}
        locale={{emptyText: '暂无通话记录'}} columns={[
          {title: '记录时间（北京时间）', dataIndex: 'recorded_at', render: beijingTime},
          {title: '记录人编号', dataIndex: 'advisor_id'},
          {title: '沟通内容', dataIndex: 'notes', render: value => <Typography.Text style={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{value}</Typography.Text>},
        ]}/>
      <HistoryPaging before={beforeCall} count={calls.data?.length}
        reset={() => setBeforeCall(undefined)} next={() => setBeforeCall(calls.data?.at(-1)?.id)}/>
    </Card>
    <Card title="游客提交的材料">
      <ErrorNotice error={materials.error}/>
      <Table size="small" rowKey="source_id" loading={materials.isFetching} pagination={false}
        dataSource={materials.data || []} locale={{emptyText: '游客尚未提交材料'}} columns={[
          {title: '材料', render: (_, row) => row.file_name || '文字资料'},
          {title: '处理进度', dataIndex: 'status', render: value => <Tag>{materialStatuses[value]}</Tag>},
          {title: '操作', render: (_, row) => <Space wrap>
            <Button type="link" onClick={() => setTarget(row.source_id)} href="#intake-screening">查看与补录</Button>
            {row.file_name && <Button type="link" loading={attachment.isPending && attachment.variables?.source_id === row.source_id}
              disabled={attachment.isPending} onClick={() => attachment.mutate(row)}>下载原件</Button>}
          </Space>},
        ]}/>
      <HistoryPaging before={beforeMaterial} count={materials.data?.length}
        reset={() => setBeforeMaterial(undefined)} next={() => setBeforeMaterial(materials.data?.at(-1)?.source_id)}/>
    </Card>
    <Card title="资料补录与初筛" id="intake-screening">
      <Space orientation="vertical" size="middle" style={{width: '100%'}}>
        <label htmlFor="screening-source">补录对应资料</label>
        <Select id="screening-source" value={target} options={targetOptions} onChange={value => {setTarget(value); difyPreview.reset()}}/>
        <ErrorNotice error={details.error}/>
        {details.isLoading ? <Typography.Text>正在读取资料…</Typography.Text> : !details.error && <>
          {details.data?.raw_content && <Alert type="info" title="游客提供的文字"
            description={<span style={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{details.data.raw_content}</span>}/>}
          {target !== 'manual' && (details.data?.raw_content || details.data?.file_name) && <>
            <Button loading={difyPreview.isPending} onClick={() => difyPreview.mutate(target)}>运行 Dify 研判</Button>
            {difyPreview.variables === target && <ErrorNotice error={difyPreview.error}/>}
            {difyPreview.variables === target && difyPreview.data && <Alert type="info" showIcon
              title="Dify 研判建议" description={<span style={{whiteSpace: 'pre-wrap'}}>{difyPreview.data.match_reason}</span>}/>}
          </>}
          {canWrite && !visitor.last_contact_at && <Alert showIcon type="info" title="保存通话记录后即可补录"/>}
          <ScreeningForm key={String(target)} initial={details.data?.screening_input} result={details.data?.screening}
            enabled={canWrite && !!visitor.last_contact_at}
            path={base + '/screening' + query({source_id: target === 'manual' ? undefined : target})}
            onSaved={sourceId => {
              if (target === 'manual') onUpdate({manual_source_id: sourceId})
              void cache.invalidateQueries({queryKey: detailsKey})
              void cache.invalidateQueries({queryKey: [...scope, visitor.visitor_id, 'materials']})
              void cache.invalidateQueries({queryKey: [...scope, 'assigned']})
            }}/>
        </>}
        {visitor.crm_lead_id && can('crm:read') &&
          <Link to="/customers">已建档 · 客户编号 {visitor.crm_lead_id}</Link>}
        {!visitor.crm_lead_id && details.data?.screening?.status === 'potential_match' && canWrite && can('crm:write') &&
          <Button onClick={() => {
            const sourceId = details.data?.source_id
            if (!sourceId) return
            setLeadAction({
              title: '确认意向并建立客户档案', path: base + '/lead', method: 'POST',
              fields: [
                {name: 'customer_name', label: '客户姓名', initial: visitor.name, required: true},
                {name: 'contact_info', label: '联系方式', initial: visitor.contact, required: true},
                {name: 'intended_major', label: '意向专业'},
                {name: 'remark', label: '回访后的意向确认', kind: 'textarea', required: true},
              ],
              transform: values => ({...values, source_id: sourceId}),
              successText: '客户档案已建立，历史通话已同步',
            })
          }}>意向客户建档</Button>}
      </Space>
    </Card>
    <ActionModal action={leadAction} onClose={() => setLeadAction(null)} onSuccess={result => {
      if (result && typeof result === 'object' && 'id' in result && typeof result.id === 'number') {
        onUpdate({crm_lead_id: result.id})
      }
    }}/>
  </Space>
}

function ScreeningForm({initial, result, enabled, path, onSaved}: {
  initial?: ScreeningInput | null; result?: ScreeningResult | null; enabled: boolean; path: string
  onSaved: (sourceId: number) => void
}) {
  const {message} = App.useApp()
  const preview = useMutation({
    mutationFn: (values: ScreeningInput) => api<{source_id: number; screening: ScreeningResult}>(path, {
      method: 'POST',
      body: Object.fromEntries(screeningFields.map(field => [field.name, values[field.name as keyof ScreeningInput] ?? null])),
    }),
    onSuccess: value => {
      onSaved(value.source_id)
      void message.success('已保存并完成初筛')
    },
  })
  const visible = preview.data?.screening ?? result
  return <>
    <Form initialValues={initial ?? {}} layout="vertical" onFinish={(values: ScreeningInput) => preview.mutate(values)}>
      <FormFields fields={screeningFields.map(field => ({...field, disabled: !enabled || preview.isPending}))}/>
      {enabled && <Button type="primary" htmlType="submit" loading={preview.isPending}>保存并研判</Button>}
    </Form>
    <ErrorNotice error={preview.error}/>
    {visible ? <Alert showIcon type={visible.status === 'potential_match' ? 'success' : 'info'}
      title={screeningStatuses[visible.status]} description={<>
        {!!visible.missing_fields.length && <div>待补充项目：{visible.missing_fields.map(field => fieldLabels[field] || field).join('、')}</div>}
        {visible.findings.map(item => <div key={item}>{item}</div>)}
      </>}/> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无研判结果"/>}
  </>
}


function HistoryPaging({before, count, reset, next}: {before?: number; count?: number; reset: () => void; next: () => void}) {
  return <Space style={{marginTop: 12}}>
    <Button disabled={before === undefined} onClick={reset}>返回最新</Button>
    <Button disabled={count !== pageSize} onClick={next}>查看更多</Button>
  </Space>
}


const advisorEndpoint = '/api/v1/profile'
type AdvisorSource = {source_id: number; file_name: string | null; submitted_at: string; screening: ScreeningResult | null}

function AdvisorMaterials({canWrite}: {canWrite: boolean}) {
  const {user} = useAuth()
  const {message} = App.useApp()
  const cache = useQueryClient()
  const file = useRef<HTMLInputElement>(null)
  const [form] = Form.useForm<{raw_content?: string}>()
  const [before, setBefore] = useState<number>()
  const [active, setActive] = useState<number>()
  const scope = [user?.id, 'advisor-materials']
  const list = useQuery({
    queryKey: [...scope, before],
    queryFn: () => api<AdvisorSource[]>(advisorEndpoint + query({before_id: before, limit: pageSize})),
  })
  const upload = useMutation({
    mutationFn: (values: {raw_content?: string}) => {
      const body = new FormData()
      const attachment = file.current?.files?.[0]
      const extension = attachment?.name.split('.').at(-1)?.toLowerCase()
      const types: Record<string, string> = {pdf: 'pdf_resume', xls: 'excel', xlsx: 'excel', csv: 'import'}
      body.append('source_type', types[extension ?? ''] ?? 'text')
      if (values.raw_content?.trim()) body.append('raw_content', values.raw_content.trim())
      if (attachment) body.append('file', attachment)
      return api<{source_id: number}>(advisorEndpoint + '/upload', {method: 'POST', body})
    },
    onSuccess: item => {
      form.resetFields()
      if (file.current) file.current.value = ''
      setBefore(undefined)
      setActive(item.source_id)
      void cache.invalidateQueries({queryKey: scope})
      void message.success('顾问资料已上传')
    },
  })
  return <Space orientation="vertical" style={{width: '100%'}}>
    {canWrite && <Form form={form} layout="vertical" onFinish={values => upload.mutate(values)}>
      <Form.Item name="raw_content" label="材料说明">
        <Input.TextArea maxLength={16000} placeholder="可粘贴单个客户的资料"/>
      </Form.Item>
      <Form.Item label="附件" htmlFor="advisor-material-file">
        <input id="advisor-material-file" ref={file} type="file" accept=".txt,.csv,.pdf,.xls,.xlsx"/>
      </Form.Item>
      <Button type="primary" htmlType="submit" loading={upload.isPending}>上传顾问资料</Button>
    </Form>}
    <ErrorNotice error={upload.error || list.error}/>
    <Table<AdvisorSource> rowKey="source_id" dataSource={list.data ?? []} loading={list.isFetching} pagination={false} columns={[
      {title: '资料', render: (_, row) => row.file_name || '文字资料'},
      {title: '上传时间（北京时间）', dataIndex: 'submitted_at', render: beijingTime},
      {title: '初筛结果', render: (_, row) => row.screening ? screeningStatuses[row.screening.status] : '待研判'},
      {title: '操作', render: (_, row) => <Button type="link" onClick={() => setActive(row.source_id)}>查看与研判</Button>},
    ]}/>
    <HistoryPaging before={before} count={list.data?.length ?? 0} reset={() => setBefore(undefined)}
      next={() => setBefore(list.data?.at(-1)?.source_id)}/>
    <Drawer title="顾问资料研判" open={active !== undefined} onClose={() => setActive(undefined)} size="large">
      {active !== undefined && <AdvisorReview key={active} id={active} canWrite={canWrite}
        onSaved={() => void cache.invalidateQueries({queryKey: scope})}/>}
    </Drawer>
  </Space>
}

function AdvisorReview({id, canWrite, onSaved}: {id: number; canWrite: boolean; onSaved: () => void}) {
  const {user} = useAuth()
  const path = advisorEndpoint + '/' + id
  const details = useQuery({queryKey: [user?.id, 'advisor-material', id], queryFn: () => api<SourceDetails>(path)})
  const preview = useMutation({mutationFn: () => api<{match_reason: string}>(path + '/dify-preview', {method: 'POST', timeout: 60000})})
  return <Space orientation="vertical" style={{width: '100%'}}>
    <ErrorNotice error={details.error || preview.error}/>
    {details.data && <>
      <Typography.Paragraph style={{whiteSpace: 'pre-wrap'}}>{details.data.raw_content}</Typography.Paragraph>
      <Button loading={preview.isPending} onClick={() => preview.mutate()}>运行 Dify 研判</Button>
      {preview.data && <Alert type="info" title="Dify 研判建议" description={preview.data.match_reason}/>}
      <ScreeningForm initial={details.data.screening_input} result={details.data.screening} enabled={canWrite}
        path={path + '/analyze'} onSaved={() => {void details.refetch(); onSaved()}}/>
    </>}
  </Space>
}
