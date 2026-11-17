import './student-experience.css'
import {StudentHome} from './StudentHome'
import {StudentLife} from './StudentLife'
import {Alert, Button, Card, Descriptions, Form, Input, Modal, Space, Table, Tag, Typography} from 'antd'
import {BellOutlined, BookOutlined, CalendarOutlined, ClockCircleOutlined, FolderOpenOutlined,
  GlobalOutlined, HeartOutlined, HomeOutlined, LineChartOutlined, MessageOutlined, RobotOutlined} from '@ant-design/icons'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {useLayoutEffect, useRef, useState, type ReactNode} from 'react'
import {AcademicDeadlines, academicDeadlineEndpoint} from './AcademicDeadlines'
import {PolicyCards, type PolicyData} from './WebsitePolicies'
import {StudentWellbeing} from './Wellbeing'
import {StudentAssistant} from './StudentAssistant'
import {ProgressPager, ProgressTable, type Progress} from './ApplicationProgress'

type LeaveRequest = {leave_type: 'sick' | 'personal' | 'emergency'; start_time: string; end_time: string; reason: string; attachment_id?: string}
type ComplaintRequest = {ticket_type?: 'complaint' | 'suggestion'; category: 'learning' | 'company'; title?: string; content: string}
type Leave = LeaveRequest & {id: number; status: string; approval_comment?: string}
type Complaint = ComplaintRequest & {id: number; status: string; solution?: string}
type Request = <T>(path: string, method?: string, body?: unknown, onText?: (text: string) => void) => Promise<T>
const prefix = '/api/v1/student'
const pageSize = 20
/* 一级导航图标：只影响展示，不参与任何业务逻辑 */
const tabIcons: Record<string, ReactNode> = {
  home: <HomeOutlined/>, guide: <RobotOutlined/>, leaves: <CalendarOutlined/>, complaints: <MessageOutlined/>,
  notifications: <BellOutlined/>, deadlines: <ClockCircleOutlined/>, progress: <LineChartOutlined/>,
  overseas: <GlobalOutlined/>, policies: <BookOutlined/>, wellbeing: <HeartOutlined/>,
  'account-records': <FolderOpenOutlined/>,
}

/* 一级导航分组：仅决定菜单的分组与顺序，Tab key 与内容保持原样 */
const navGroups: {title: string; keys: string[]}[] = [
  {title: '概览', keys: ['home', 'guide']},
  {title: '申请与学业', keys: ['progress', 'deadlines', 'policies']},
  {title: '日常事务', keys: ['leaves', 'complaints', 'notifications']},
  {title: '海外支持', keys: ['overseas', 'wellbeing']},
  {title: '我的记录', keys: ['account-records']},
]

const statuses: Record<string, string> = {
  pending: '待处理', approved: '已通过', rejected: '已拒绝',
  cancelled: '已取消', processing: '处理中', resolved: '已解决', closed: '已关闭',
}

export function Student({request, accountRecords}: {request: Request; accountRecords: ReactNode}) {
  const [activeTab, setActiveTab] = useState('home')
  const main = useRef<HTMLDivElement>(null)
  const launchCount = useRef(0)
  const [launch, setLaunch] = useState<{id: number; query: string}>()
  function chat(query?: string) {
    setActiveTab('guide')
    if (query) setLaunch({id: ++launchCount.current, query})
  }
  useLayoutEffect(() => {
    if (main.current) main.current.scrollTop = 0
  }, [activeTab])
  const profile = useQuery({
    queryKey: ['visitor', 'student', 'profile'],
    queryFn: () => request<{abroad_country: string | null}>(prefix + '/profile'),
  })
  const country = profile.data?.abroad_country
  const nextDeadline = useQuery({
    queryKey: ['visitor', 'student', 'deadlines', 'next'],
    queryFn: () => request<{items: {title: string; deadline: string}[]}>(academicDeadlineEndpoint + '?limit=1'),
    refetchOnWindowFocus: true,
    refetchInterval: 60000,
  }).data?.items?.[0]
  const destination = country === 'Singapore' ? '新加坡' : country === 'Germany' ? '德国' : country
  /* children 与 Tab key 完全沿用原实现，只把「标签的呈现方式」换成左侧分组导航 */
  const tabs: {key: string; label: string; children: ReactNode}[] = [
    {key: 'home', label: '欢迎首页', children: <StudentHome request={request} open={setActiveTab} chat={chat}/>},
    {key: 'guide', label: '学生助手', children: <StudentAssistant request={request} launch={launch}/>},
    {key: 'leaves', label: '请假申请', children: <Leaves request={request}/>},
    {key: 'complaints', label: '投诉反馈', children: <Complaints request={request}/>},
    {key: 'notifications', label: '站内通知', children: <StudentNotifications request={request}/>},
    {key: 'deadlines', label: '考务提醒', children: <AcademicDeadlines request={request}/>},
    {key: 'progress', label: '申请进度', children: <MyProgress request={request}/>},
    {key: 'overseas', label: '海外生活', children: <StudentLife request={request} chat={chat}/>},
    {key: 'policies', label: '留学政策', children: <Policies request={request}/>},
    {key: 'wellbeing', label: '自评与关怀', children: <StudentWellbeing request={request}/>},
    {key: 'account-records', label: '我的材料与活动', children: accountRecords},
  ]
  const current = tabs.find(tab => tab.key === activeTab) ?? tabs[0]
  return <section className={'visitor-section student-page' + (activeTab === 'guide' ? ' student-page--chat' : '')}>
    <div className="student-shell">
      <aside className="student-side" aria-label="学生服务导航">
        {navGroups.map(group => <div className="student-nav-group" key={group.title}>
          <div className="student-nav-label">{group.title}</div>
          {group.keys.map(key => {
            const tab = tabs.find(item => item.key === key)!
            return <button type="button" key={key}
              className={'student-nav-item' + (activeTab === key ? ' active' : '')}
              aria-current={activeTab === key ? 'page' : undefined}
              aria-label={tab.label + (key === 'deadlines' && nextDeadline ? '，有近期事项' : '')}
              onClick={() => setActiveTab(key)}>
              <span className="student-nav-icon">{tabIcons[key]}</span>{tab.label}{key === 'deadlines' && nextDeadline && <span className="student-nav-dot" aria-hidden="true"/>}
            </button>
          })}
        </div>)}
        <div className="student-side-foot">想找答案、安排事情，或聊聊近况，都可以从这里开始。</div>
      </aside>
      <div ref={main} className={'student-main' + (activeTab === 'guide' ? ' student-main--assistant' : activeTab === 'home' ? ' student-main--home' : '')} role="region" aria-label="学生服务内容" tabIndex={0}>
        <header className="student-head">
          <div>
            <span className="student-eyebrow">学生服务中心</span>
            <h1>学生服务</h1>
            <p>{destination ? '留学地区：' + destination : '在这里办理请假、查看进度与考务提醒'}</p>
          </div>
          <span className="student-head-meta">当前模块 · <b>{current.label}</b></span>
        </header>
        <ResultNotice error={profile.error}/>

        <div className="student-panel student-panel--assistant" style={activeTab === 'guide' ? undefined : {display: 'none'}}>
          {tabs.find(tab => tab.key === 'guide')?.children}
        </div>
        {activeTab !== 'guide' && <div className="student-panel">{current.children}</div>}
        {activeTab === 'account-records' && <div className="student-helper-grid">
          <section className="student-helper">
            <h4>活动与材料提示</h4>
            <ul>
              <li>讲座名额有限，预约后请留意站内通知与签到时间。</li>
              <li>材料可先提交已有版本，顾问确认后再补正式清单。</li>
              <li>申请有更新时，可在「申请进度」查看当前阶段与下一步。</li>
            </ul>
          </section>
          <section className="student-helper student-helper--dark">
            <h4>需要帮助？</h4>
            <p>不确定该预约哪场讲座、或材料怎么交，可以直接问学生助手。</p>
            <Button onClick={() => setActiveTab('guide')}>去问学生助手</Button>
          </section>
        </div>}
      </div>
    </div>
  </section>
}

type StudentNotification = {
  id: number; title: string; content: string; create_time: string
  related_summary?: string | null
  related_details?: {title: string; fields: {label: string; value: string}[]} | null
}

function StudentNotifications({request}: {request: Request}) {
  const [beforeId, setBeforeId] = useState<number>()
  const [selected, select] = useState<StudentNotification>()
  const notices = useQuery({
    queryKey: ['visitor', 'student', 'notifications', beforeId],
    queryFn: () => request<StudentNotification[]>(prefix + '/notifications?limit=20' + (beforeId ? '&before_id=' + beforeId : '')),
    refetchOnWindowFocus: true,
    refetchInterval: 30000,
  })
  return <Card title="站内通知">
    <ResultNotice error={notices.error}/>
    <Table rowKey="id" dataSource={notices.data || []} loading={notices.isFetching} pagination={false} scroll={{x: 820}}
      locale={{emptyText: '暂无通知'}} columns={[
        {title: '标题', dataIndex: 'title', width: 140}, {title: '内容', dataIndex: 'content', width: 200},
        {title: '关联事项', width: 300, render: (_, row) => <>
          <Typography.Paragraph style={{marginBottom: 4}}>{row.related_summary || '关联记录暂不可用'}</Typography.Paragraph>
          {row.related_details && <Button type="link" style={{padding: 0}} onClick={() => select(row)}>查看详情</Button>}
        </>},
        {title: '时间', width: 180, render: (_, row) => row.create_time.replace('T', ' ')},
      ]}/>
    <Pager beforeId={beforeId} rows={notices.data} move={setBeforeId}/>
    <Modal title={selected?.related_details?.title} open={!!selected} onCancel={() => select(undefined)}
      footer={<Button onClick={() => select(undefined)}>关闭</Button>}>
      <Typography.Paragraph>{selected?.content}</Typography.Paragraph>
      <Descriptions column={1} items={selected?.related_details?.fields.map((field, index) => ({
        key: String(index), label: field.label, children: <span style={{whiteSpace: 'pre-wrap'}}>{field.value}</span>,
      }))}/>
    </Modal>
  </Card>
}

function MyProgress({request}: {request: Request}) {
  const [before, move] = useState<number>()
  const records = useQuery({
    queryKey: ['visitor', 'student', 'application-progress', before],
    queryFn: () => request<Progress[]>(prefix + '/application-progress?limit=20' + (before ? '&before_id=' + before : '')),
  })
  return <Card title="我的院校申请进度">
    <Typography.Paragraph type="secondary">这里查看院校、专业及录取或签证办理阶段。请假审批和投诉处理结果请到对应栏目查看。</Typography.Paragraph>
    <ResultNotice error={records.error}/>
    <ProgressTable rows={records.data} loading={records.isFetching}/>
    <ProgressPager before={before} rows={records.data} move={move}/>
  </Card>
}

function Policies({request}: {request: Request}) {
  const result = useQuery({
    queryKey: ['visitor', 'student', 'policies'],
    queryFn: () => request<PolicyData>(prefix + '/policies'),
    staleTime: 0,
    refetchOnWindowFocus: true,
  })
  if (result.error) return <ResultNotice error={result.error}/>
  if (result.isPending) return <Typography.Text>正在读取留学政策…</Typography.Text>
  if (!result.data?.country) return <Alert type="info" showIcon title="请联系老师确认学籍中的留学地区"/>
  return <PolicyCards resources={result.data.resources}/>
}

function useStudentRecords<RecordType, Fields>(request: Request, kind: 'leaves' | 'complaints') {
  const [beforeId, setBeforeId] = useState<number>()
  const [form] = Form.useForm<Fields>()
  const cache = useQueryClient()
  const key = ['visitor', 'student', kind]
  const url = prefix + '/' + kind
  const history = useQuery({
    queryKey: [...key, beforeId],
    queryFn: () => request<RecordType[]>(url + '?limit=' + pageSize + (beforeId ? '&before_id=' + beforeId : '')),
  })
  const submit = useMutation({
    mutationFn: (values: Fields) => request<RecordType>(url, 'POST', values),
    onSuccess: () => {
      form.resetFields()
      setBeforeId(undefined)
      void cache.invalidateQueries({queryKey: key})
    },
  })
  return {beforeId, setBeforeId, form, history, submit}
}

function Leaves({request}: {request: Request}) {
  const {beforeId, setBeforeId, form, history, submit} = useStudentRecords<Leave, LeaveRequest>(request, 'leaves')
  const [proof, setProof] = useState<{id: string; filename: string}>()
  const [proofBusy, setProofBusy] = useState(false)
  const [proofError, setProofError] = useState<Error>()
  const [fileKey, setFileKey] = useState(0)
  async function uploadProof(file?: File) {
    setProof(undefined)
    setProofError(undefined)
    if (!file) return
    if (file.size > 5 * 1024 * 1024) {
      setProofError(new Error('附件须小于5MB'))
      return
    }
    const payload = new FormData()
    payload.set('file', file)
    setProofBusy(true)
    try {setProof(await request<{id: string; filename: string}>(prefix + '/leaves/attachments', 'POST', payload))}
    catch (error) {setProofError(error as Error)}
    finally {setProofBusy(false)}
  }
  return <Space orientation="vertical" size="large" style={{width: '100%'}}>
    <Card title="提交请假">
      <Form form={form} layout="vertical" onFinish={value => submit.mutate({...value, attachment_id: proof?.id}, {
        onSuccess: () => {setProof(undefined); setProofError(undefined); setFileKey(key => key + 1)},
      })} style={{maxWidth: 520}}>
        <Form.Item label="请假类型" name="leave_type" rules={[{required: true}]}>
          <select className="ant-input"><option value="">请选择</option><option value="sick">病假</option>
            <option value="personal">事假</option><option value="emergency">紧急事由</option></select>
        </Form.Item>
        <Form.Item label="开始时间（北京时间）" name="start_time" rules={[{required: true}]}><Input type="datetime-local"/></Form.Item>
        <Form.Item label="结束时间（北京时间）" name="end_time" rules={[{required: true}]}><Input type="datetime-local"/></Form.Item>
        <Form.Item label="请假原因" name="reason" rules={[{required: true, whitespace: true}]}><Input.TextArea maxLength={4000}/></Form.Item>
        <Form.Item label="证明附件（可选，PDF、JPG或PNG，5MB以内）">
          <input key={fileKey} aria-label="请假证明附件" type="file" accept=".pdf,.jpg,.jpeg,.png" disabled={proofBusy || submit.isPending}
            onChange={event => void uploadProof(event.target.files?.[0])}/>
          {proof && <p>已上传 {proof.filename}</p>}
          <ResultNotice error={proofError ?? null}/>
        </Form.Item>
        <Button type="primary" htmlType="submit" loading={submit.isPending} disabled={proofBusy}>提交请假</Button>
      </Form>
      <ResultNotice error={submit.error} sent={submit.isSuccess}/>
    </Card>
    <Card title="我的请假">
      <ResultNotice error={history.error}/>
      <Table rowKey="id" dataSource={history.data || []} loading={history.isFetching} pagination={false}
        scroll={{x: 630}} locale={{emptyText: '暂无请假记录'}} columns={[
          {title: '请假单', render: (_, row) => <>{'请假单 #' + row.id}<br/>{({sick: '病假', personal: '事假', emergency: '紧急事由'}[row.leave_type])}</>},
          {title: '起止时间', render: (_, row) => row.start_time?.replace('T', ' ') + ' 至 ' + row.end_time?.replace('T', ' ')},
          {title: '原因', dataIndex: 'reason'},
          {title: '状态', render: (_, row) => <Tag>{statuses[row.status] || row.status}</Tag>},
          {title: '审批意见', render: (_, row) => row.approval_comment || '—'},
        ]}/>
      <Pager beforeId={beforeId} rows={history.data} move={setBeforeId}/>
    </Card>
  </Space>
}

function Complaints({request}: {request: Request}) {
  const {beforeId, setBeforeId, form, history, submit} = useStudentRecords<Complaint, ComplaintRequest>(request, 'complaints')
  return <Space orientation="vertical" size="large" style={{width: '100%'}}>
    <Card title="提交投诉或建议">
      <Form form={form} layout="vertical" onFinish={value => submit.mutate(value)} style={{maxWidth: 520}}>
        <Form.Item label="反馈方式" name="ticket_type" initialValue="complaint"><select className="ant-input"><option value="complaint">正式投诉</option><option value="suggestion">提出建议</option></select></Form.Item>
        <Form.Item label="反馈类别" name="category" rules={[{required: true}]}>
          <select className="ant-input"><option value="">请选择</option>
            <option value="learning">学习相关（交老师处理）</option><option value="company">公司相关（交主管处理）</option></select>
        </Form.Item>
        <Form.Item label="标题" name="title"><Input maxLength={255}/></Form.Item>
        <Form.Item label="反馈内容" name="content" rules={[{required: true, whitespace: true}]}><Input.TextArea maxLength={10000}/></Form.Item>
        <Button type="primary" htmlType="submit" loading={submit.isPending}>提交反馈</Button>
      </Form>
      <ResultNotice error={submit.error} sent={submit.isSuccess}/>
    </Card>
    <Card title="我的反馈">
      <ResultNotice error={history.error}/>
      <Table rowKey="id" dataSource={history.data || []} loading={history.isFetching} pagination={false}
        scroll={{x: 650}} locale={{emptyText: '暂无反馈记录'}} columns={[
          {title: '方式', render: (_, row) => (row.ticket_type ? ({complaint: '投诉', suggestion: '建议'}[row.ticket_type] || '反馈') : '反馈')},
          {title: '类别', render: (_, row) => ({learning: '学习相关', company: '公司相关'}[row.category] || '—')},
          {title: '内容', render: (_, row) => row.title ? <><strong>{row.title}</strong><br/>{row.content}</> : row.content},
          {title: '状态', render: (_, row) => <Tag>{statuses[row.status] || row.status}</Tag>},
          {title: '处理结果', render: (_, row) => row.solution || '—'},
        ]}/>
      <Pager beforeId={beforeId} rows={history.data} move={setBeforeId}/>
    </Card>
  </Space>
}

function ResultNotice({error, sent}: {error: Error | null; sent?: boolean}) {
  if (error) return <Alert type="error" showIcon title={error.message} style={{marginTop: 12}}/>
  return sent ? <Alert type="success" showIcon title="已提交，可以在列表中查看处理进度" style={{marginTop: 12}}/> : null
}

function Pager({beforeId, rows, move}: {beforeId?: number; rows?: {id: number}[]; move: (id?: number) => void}) {
  return <Space style={{marginTop: 12}}>
    <Button disabled={!beforeId} onClick={() => move()}>返回最新</Button>
    <Button disabled={rows?.length !== pageSize} onClick={() => move(rows?.at(-1)?.id)}>查看更多</Button>
  </Space>
}
