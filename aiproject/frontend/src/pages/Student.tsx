import {Alert, Button, Card, Form, Input, Space, Table, Tabs, Tag, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {useState, type ReactNode} from 'react'
import {AcademicDeadlines, academicDeadlineEndpoint} from './AcademicDeadlines'
import {PolicyCards, type PolicyData} from './WebsitePolicies'
import {WebsiteGuide, type GuideTopic} from './WebsiteGuide'
import {StudentWellbeing} from './Wellbeing'
import {StudentAssistant} from './StudentAssistant'
import {ProgressPager, ProgressTable, type Progress} from './ApplicationProgress'

type LeaveRequest = {leave_type: 'sick' | 'personal' | 'emergency'; start_time: string; end_time: string; reason: string}
type ComplaintRequest = {category: 'learning' | 'company'; title?: string; content: string}
type Leave = LeaveRequest & {id: number; status: string; approval_comment?: string}
type Complaint = ComplaintRequest & {id: number; status: string; solution?: string}
type Request = <T>(path: string, method?: string, body?: unknown) => Promise<T>
const prefix = '/api/v1/student'
const pageSize = 20
const studentTopics: GuideTopic[] = [
  {key: 'leaves', label: '请假申请', keywords: ['请假', '病假', '事假'], answer: '填写请假时间和原因，老师审批后可在站内通知查看结果。'},
  {key: 'complaints', label: '投诉反馈', keywords: ['投诉', '反馈'], answer: '学习相关投诉交老师处理，公司相关投诉交主管处理。'},
  {key: 'deadlines', label: '考务提醒', keywords: ['考试', '考务', '论文', '截止', '考期'], answer: '查看即将截止的考务待办，办完后可标记个人事项。'},
  {key: 'progress', label: '申请进度', keywords: ['申请', '录取', '进度'], answer: '查看顾问更新的申请阶段、截止时间和下一步。'},
  {key: 'policies', label: '留学政策', keywords: ['政策', '签证', '准证'], answer: '查找学籍中对应留学地区的官方政策入口。'},
  {key: 'overseas', label: '海外生活', keywords: ['生活', '交通', '医疗', '求助'], answer: '查询学籍中对应地区的海外生活资料。'},
  {key: 'notifications', label: '站内通知', keywords: ['通知', '消息', '审批'], answer: '查阅请假审批或投诉处理结果。'},
]

const statuses: Record<string, string> = {
  pending: '待处理', approved: '已通过', rejected: '已拒绝',
  cancelled: '已取消', processing: '处理中', resolved: '已解决', closed: '已关闭',
}

export function Student({request, accountRecords}: {request: Request; accountRecords: ReactNode}) {
  const [activeTab, setActiveTab] = useState('guide')
  const profile = useQuery({
    queryKey: ['visitor', 'student', 'profile'],
    queryFn: () => request<{abroad_country: string | null}>(prefix + '/profile'),
  })
  const nextDeadline = useQuery({
    queryKey: ['visitor', 'student', 'deadlines', 'next'],
    queryFn: () => request<{items: {title: string; deadline: string}[]}>(academicDeadlineEndpoint + '?limit=1'),
    refetchOnWindowFocus: true,
    refetchInterval: 60000,
  }).data?.items?.[0]
  const country = profile.data?.abroad_country
  const destination = country === 'Singapore' ? '新加坡' : country === 'Germany' ? '德国' : country
  return <section className="visitor-section">
    <Typography.Title level={2}>学生服务</Typography.Title>
    {destination && <Typography.Paragraph>留学地区：{destination}</Typography.Paragraph>}
    <ResultNotice error={profile.error}/>
    {nextDeadline && <Alert type="warning" showIcon title={nextDeadline.title}
      description={'截止时间（北京时间）' + nextDeadline.deadline.slice(0, 16).replace('T', ' ')}
      action={<Button onClick={() => setActiveTab('deadlines')}>查看考务</Button>}/>}
    <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
      {key: 'guide', label: '学生助手', children: <>
        <StudentAssistant request={request}/>
        <WebsiteGuide topics={studentTopics} open={setActiveTab}/>
      </>},
      {key: 'leaves', label: '请假申请', children: <Leaves request={request}/>},
      {key: 'complaints', label: '投诉反馈', children: <Complaints request={request}/>},
      {key: 'notifications', label: '站内通知', children: <StudentNotifications request={request}/>},
      {key: 'deadlines', label: '考务提醒', children: <AcademicDeadlines request={request}/>},
      {key: 'progress', label: '申请进度', children: <MyProgress request={request}/>},
      {key: 'overseas', label: '海外生活', children: <OverseasLife request={request}/>},
      {key: 'policies', label: '留学政策', children: <Policies request={request}/>},
      {key: 'wellbeing', label: '自评与关怀', children: <StudentWellbeing request={request}/>},
      {key: 'account-records', label: '我的材料与活动', children: accountRecords},
    ]}/>
  </section>
}

type StudentNotification = {id: number; title: string; content: string; create_time: string}

function StudentNotifications({request}: {request: Request}) {
  const [beforeId, setBeforeId] = useState<number>()
  const notices = useQuery({
    queryKey: ['visitor', 'student', 'notifications', beforeId],
    queryFn: () => request<StudentNotification[]>(prefix + '/notifications?limit=20' + (beforeId ? '&before_id=' + beforeId : '')),
    refetchOnWindowFocus: true,
    refetchInterval: 30000,
  })
  return <Card title="站内通知">
    <ResultNotice error={notices.error}/>
    <Table rowKey="id" dataSource={notices.data || []} loading={notices.isFetching} pagination={false}
      locale={{emptyText: '暂无通知'}} columns={[
        {title: '标题', dataIndex: 'title'}, {title: '内容', dataIndex: 'content'},
        {title: '时间', render: (_, row) => row.create_time.replace('T', ' ')},
      ]}/>
    <Pager beforeId={beforeId} rows={notices.data} move={setBeforeId}/>
  </Card>
}

function MyProgress({request}: {request: Request}) {
  const [before, move] = useState<number>()
  const records = useQuery({
    queryKey: ['visitor', 'student', 'application-progress', before],
    queryFn: () => request<Progress[]>(prefix + '/application-progress?limit=20' + (before ? '&before_id=' + before : '')),
  })
  return <Card title="我的申请进度">
    <ResultNotice error={records.error}/>
    <ProgressTable rows={records.data} loading={records.isFetching}/>
    <ProgressPager before={before} rows={records.data} move={move}/>
  </Card>
}

type OverseasResource = {id: number; title: string; category: string; content: string}

function OverseasLife({request}: {request: Request}) {
  const [keyword, search] = useState('')
  const [afterId, setAfterId] = useState(0)
  const result = useQuery({
    queryKey: ['visitor', 'student', 'overseas', keyword, afterId],
    queryFn: () => request<{items: OverseasResource[]; next_after_id: number | null}>(
      prefix + '/overseas-life?' + new URLSearchParams({keyword, after_id: String(afterId)})),
  })
  const categories: Record<string, string> = {medical: '医疗', transport: '交通', emergency: '紧急求助', daily_life: '生活', other: '其他'}
  return <Space orientation="vertical" size="middle" style={{width: '100%'}}>
    <Input.Search aria-label="查询海外生活资料" placeholder="搜索医疗、交通或生活资料"
      maxLength={64} allowClear onSearch={value => {search(value.trim()); setAfterId(0)}}/>
    <ResultNotice error={result.error}/>
    {!result.isFetching && !result.error && !result.data?.items.length &&
      <Alert type="info" showIcon title="暂无符合条件的本地区生活资料"/>}
    <div className="visitor-programs">
      {(result.data?.items || []).map(item => <Card key={item.id} title={item.title} extra={<Tag>{categories[item.category]}</Tag>}>
        <Typography.Paragraph style={{whiteSpace: 'pre-wrap'}}>{item.content}</Typography.Paragraph>
      </Card>)}
    </div>
    <Space>
      <Button disabled={!afterId || result.isFetching} onClick={() => setAfterId(0)}>返回首批</Button>
      <Button disabled={!result.data?.next_after_id || result.isFetching}
        onClick={() => setAfterId(result.data?.next_after_id ?? afterId)}>查看更多</Button>
    </Space>
  </Space>
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
  return <Space orientation="vertical" size="large" style={{width: '100%'}}>
    <Card title="提交请假">
      <Form form={form} layout="vertical" onFinish={value => submit.mutate(value)} style={{maxWidth: 520}}>
        <Form.Item label="请假类型" name="leave_type" rules={[{required: true}]}>
          <select className="ant-input"><option value="">请选择</option><option value="sick">病假</option>
            <option value="personal">事假</option><option value="emergency">紧急事由</option></select>
        </Form.Item>
        <Form.Item label="开始时间（北京时间）" name="start_time" rules={[{required: true}]}><Input type="datetime-local"/></Form.Item>
        <Form.Item label="结束时间（北京时间）" name="end_time" rules={[{required: true}]}><Input type="datetime-local"/></Form.Item>
        <Form.Item label="请假原因" name="reason" rules={[{required: true, whitespace: true}]}><Input.TextArea maxLength={4000}/></Form.Item>
        <Button type="primary" htmlType="submit" loading={submit.isPending}>提交请假</Button>
      </Form>
      <ResultNotice error={submit.error} sent={submit.isSuccess}/>
    </Card>
    <Card title="我的请假">
      <ResultNotice error={history.error}/>
      <Table rowKey="id" dataSource={history.data || []} loading={history.isFetching} pagination={false}
        scroll={{x: 630}} locale={{emptyText: '暂无请假记录'}} columns={[
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
    <Card title="提交投诉">
      <Form form={form} layout="vertical" onFinish={value => submit.mutate(value)} style={{maxWidth: 520}}>
        <Form.Item label="投诉类别" name="category" rules={[{required: true}]}>
          <select className="ant-input"><option value="">请选择</option>
            <option value="learning">学习相关（交老师处理）</option><option value="company">公司相关（交主管处理）</option></select>
        </Form.Item>
        <Form.Item label="标题" name="title"><Input maxLength={255}/></Form.Item>
        <Form.Item label="投诉内容" name="content" rules={[{required: true, whitespace: true}]}><Input.TextArea maxLength={10000}/></Form.Item>
        <Button type="primary" htmlType="submit" loading={submit.isPending}>提交投诉</Button>
      </Form>
      <ResultNotice error={submit.error} sent={submit.isSuccess}/>
    </Card>
    <Card title="我的投诉">
      <ResultNotice error={history.error}/>
      <Table rowKey="id" dataSource={history.data || []} loading={history.isFetching} pagination={false}
        scroll={{x: 580}} locale={{emptyText: '暂无投诉记录'}} columns={[
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
