import {useState} from 'react'
import {Navigate, useLocation, useNavigate} from 'react-router-dom'
import {Student} from './Student'
import {WebsiteCourses} from './WebsiteCourses'
import {WebsitePolicies} from './WebsitePolicies'
import {WebsiteGuide, type GuideTopic} from './WebsiteGuide'
import {WebsiteAssistant} from './WebsiteAssistant'
import {Alert, App, Button, Card, Form, Input, List, Space, Tabs, Tag, Typography} from 'antd'
import {useQuery, useQueryClient} from '@tanstack/react-query'

type Activity = {
  id: number; event_name: string; description?: string; location: string | null; start_time: string; end_time: string | null
  current_participants: number; max_participants: number | null; reservation_status?: string
}
type Booking = {event: Activity; reservation: {id: number; status: string}}
type Material = {source_id: number; file_name: string | null; submitted_at: string; status: string}
type WebsiteIdentity = {account_type: 'visitor' | 'student'}
type Credentials = {username: string; password: string; name?: string; contact?: string}

const publicTopics: GuideTopic[] = [
  {key: 'events', label: '活动预约', keywords: ['活动', '预约', '讲座'], answer: '注册并登录后可查看线下讲座时间和名额，也可在线取消预约。'},
  {key: 'materials', label: '材料提交', keywords: ['材料', '文件', '上传', '资料'], answer: '可以先提交已有材料，顾问会联系确认其他资料。'},
  {key: 'courses', label: '课程与项目', keywords: ['课程', '项目', '德国', '新加坡'], answer: '官网介绍新加坡升学和德国职业培训项目，登录后可查询已发布的课程与项目。'},
  {key: 'policies', label: '留学政策', keywords: ['政策', '签证', '准证'], answer: '登录后可按国家查看政策及官方办理入口。'},
]

const storageKey = 'yujiao-visitor-token'
const activityUrl = '/api/v1/visitor/events'
const materialUrl = '/api/v1/visitor/materials'
const statusNames: Record<string, string> = {
  registered: '已预约', cancelled: '已取消', attended: '已签到',
  received: '已收到', needs_information: '待补充', reviewed: '已研判',
}

function displayTime(value: string) {
  return value.slice(0, 16).replace('T', ' ')
}

class VisitorApiError extends Error {
  status: number
  constructor(message: string, status: number) {
    super(message)
    this.status = status
  }
}

async function visitorApi<T>(path: string, token: string, method = 'GET', body?: unknown): Promise<T> {
  const isFile = body instanceof FormData
  const response = await fetch(path, {
    method,
    headers: {
      ...(token ? {Authorization: 'Bearer ' + token} : {}),
      ...(body !== undefined && !isFile ? {'Content-Type': 'application/json'} : {}),
    },
    body: isFile ? body : body === undefined ? undefined : JSON.stringify(body),
    signal: AbortSignal.timeout(30000),
  })
  const result = await response.json().catch(() => ({}))
  if (!response.ok || result.code !== 0) {
    const detail = result.detail || result.message
    throw new VisitorApiError(Array.isArray(detail)
      ? detail.map(d => d.msg).join('；')
      : typeof detail === 'string' ? detail : '操作未完成，请重试', response.status)
  }
  return result.data as T
}

export function Visitor() {
  const [token, setToken] = useState(() => sessionStorage.getItem(storageKey) || '')
  const current = useLocation()
  const navigate = useNavigate()
  const identity = useQuery({
    queryKey: ['visitor', 'identity', token], enabled: !!token,
    queryFn: () => visitorApi<WebsiteIdentity>('/api/v1/visitors/me', token),
    staleTime: 0, refetchOnWindowFocus: true,
  })
  const [register, setRegister] = useState(false)
  const [authBusy, setAuthBusy] = useState(false)
  const [form] = Form.useForm<Credentials>()
  const {message} = App.useApp()
  const cache = useQueryClient()

  function clearSession() {
    sessionStorage.removeItem(storageKey)
    setToken('')
    void cache.cancelQueries({queryKey: ['visitor']})
    cache.removeQueries({queryKey: ['visitor']})
    void navigate('/website', {replace: true})
  }

  async function signIn(values: Credentials) {
    setAuthBusy(true)
    try {
      const result = await visitorApi<WebsiteIdentity & {access_token: string}>(
        '/api/v1/visitors/' + (register ? 'register' : 'login'), '', 'POST', values,
      )
      sessionStorage.setItem(storageKey, result.access_token)
      cache.setQueryData(['visitor', 'identity', result.access_token], {account_type: result.account_type})
      setToken(result.access_token)
      void navigate(result.account_type === 'student' ? '/website/student' : '/website/visitor', {replace: true})
      form.resetFields()
    } catch (error) {
      void message.error((error as Error).message)
    } finally {
      setAuthBusy(false)
    }
  }

  async function signOut() {
    setAuthBusy(true)
    try {
      await visitorApi('/api/v1/visitors/logout', token, 'POST')
      clearSession()
    } catch (error) {
      if (error instanceof VisitorApiError && error.status === 401) clearSession()
      else void message.error('退出暂未完成，请重试')
    } finally {
      setAuthBusy(false)
    }
  }

  const identityExpired = identity.error instanceof VisitorApiError && identity.error.status === 401
  const publicPath = current.pathname.replace(/\/$/, '')
  if (!token && publicPath !== '/website') return <Navigate to="/website" replace/>
  if (token && identity.error) {
    return <main className="visitor-site"><section className="visitor-section">
      <Alert type="error" showIcon title={identityExpired ? '官网登录已失效' : identity.error.message}/>
      <Space style={{marginTop: 12}}>
        <Button onClick={clearSession}>返回登录</Button>
        {!identityExpired && <Button onClick={() => void identity.refetch()}>重试</Button>}
      </Space>
    </section></main>
  }
  const accountType = identity.data?.account_type
  const entry = accountType === 'student' ? '/website/student' : '/website/visitor'
  if (token && accountType && publicPath !== entry) return <Navigate to={entry} replace/>
  if (token && !accountType) return <main className="visitor-site"><section className="visitor-section">正在核对官网身份…</section></main>
  const expire = () => {
    if (sessionStorage.getItem(storageKey) === token) clearSession()
  }
  if (token && accountType === 'student') {
    const request = <T,>(path: string, method?: string, body?: unknown) => visitorApi<T>(path, token, method, body)
      .catch((error: unknown) => {
        if (error instanceof VisitorApiError && (error.status === 401 || error.status === 403)) void identity.refetch()
        throw error
      })
    return <main className="visitor-site">
      <header className="visitor-header"><a href="/website">粤教教育服务</a>
        <Button loading={authBusy} onClick={() => void signOut()}>退出登录</Button></header>
      <Student request={request} accountRecords={<VisitorServices token={token} expire={expire}/>}/>
    </main>
  }
  return <main className="visitor-site">
    <header className="visitor-header">
      <a href="/website">粤教教育服务</a>
      <Space wrap>
        <a href="#about">关于粤教</a>
        <a href="#programs">留学项目</a>
        <a href="#visitor-services">游客服务</a>
        {token && <Button loading={authBusy} onClick={() => void signOut()}>退出登录</Button>}
      </Space>
    </header>

    <section className="visitor-intro">
      <Typography.Title>了解留学项目，预约线下讲座</Typography.Title>
      <Typography.Paragraph>查看新加坡和德国项目，向顾问提交已有材料，跟踪处理进度。</Typography.Paragraph>
      <Button type="primary" size="large" href="#visitor-services">{token ? '查看活动和资料' : '登录或注册'}</Button>
    </section>

    <section id="about" className="visitor-section">
      <Typography.Title level={2}>关于粤教</Typography.Title>
      <div className="visitor-programs">
        <Card title="留学与升学服务">
          了解新加坡升学和德国职业培训项目。注册后可预约讲座、提交手头已有的材料，由顾问跟进。
        </Card>
        <Card title="数字化服务">
          官网集中提供政策、课程和活动查询。顾问工作台汇总材料和跟进记录，方便顾问核对资料和补录。
        </Card>
      </div>
    </section>

    <section id="programs" className="visitor-section">
      <Typography.Title level={2}>留学项目</Typography.Title>
      <div className="visitor-programs">
        <Card title="新加坡国际本硕升学计划">
          提供面向不同学历阶段的升学路径，以及酒店和航空方向的就业项目。
        </Card>
        <Card title="中德精英人才共建计划">
          了解德国双元制职业培训和企业匹配流程，项目包含语言学习与岗位准备。
        </Card>
      </div>
    </section>

    <section id="visitor-services" className="visitor-section">
      <Typography.Title level={2}>游客服务</Typography.Title>
      {!token && <>
        <WebsiteAssistant title="官网客服" ask={query => visitorApi('/api/cs/chat', '', 'POST', {query})}/>
        <WebsiteGuide topics={publicTopics}/>
      </>}
      {token ? <VisitorServices token={token} expire={expire}/> : <Card className="visitor-login" title={register ? '注册游客账号' : '官网登录'}>
        <Form key={String(register)} form={form} layout="vertical" preserve={false} onFinish={v => void signIn(v)}>
          <Form.Item label="用户名" name="username" rules={[{required: true}]}>
            <Input autoComplete="username" maxLength={64}/>
          </Form.Item>
          <Form.Item label="密码" name="password" rules={[{required: true, min: register ? 8 : 1}]}>
            <Input.Password autoComplete={register ? 'new-password' : 'current-password'} maxLength={128}/>
          </Form.Item>
          {register && <>
            <Form.Item label="姓名" name="name" rules={[{required: true, whitespace: true}]}>
              <Input maxLength={64}/>
            </Form.Item>
            <Form.Item label="联系方式" name="contact" rules={[{required: true, whitespace: true}]}>
              <Input maxLength={128}/>
            </Form.Item>
          </>}
          <Space wrap>
            <Button type="primary" htmlType="submit" loading={authBusy}>{register ? '注册' : '登录'}</Button>
            <Button type="link" disabled={authBusy} onClick={() => {form.resetFields(); setRegister(!register)}}>
              {register ? '已有账号，去登录' : '注册游客账号'}
            </Button>
          </Space>
        </Form>
      </Card>}
    </section>
  </main>
}

function VisitorServices({token, expire}: {token: string; expire: () => void}) {
  const [activeTab, setActiveTab] = useState('events')
  const [offset, setOffset] = useState(0)
  const [bookingBefore, setBookingBefore] = useState<number>()
  const [materialBefore, setMaterialBefore] = useState<number>()
  const [busy, setBusy] = useState<number>()
  const [uploading, setUploading] = useState(false)
  const cache = useQueryClient()
  const {message} = App.useApp()
  const load = <T,>(path: string) => visitorApi<T>(path, token).catch((error: unknown) => {
    if (error instanceof VisitorApiError && error.status === 401) expire()
    throw error
  })
  const activities = useQuery({
    queryKey: ['visitor', 'activities', offset],
    queryFn: () => load<Activity[]>(activityUrl + '?offset=' + offset + '&limit=20'),
  })
  const bookings = useQuery({
    queryKey: ['visitor', 'bookings', bookingBefore],
    queryFn: () => load<Booking[]>(activityUrl + '/reservations?limit=20' + (bookingBefore ? '&before_id=' + bookingBefore : '')),
  })
  const materials = useQuery({
    queryKey: ['visitor', 'materials', materialBefore],
    queryFn: () => load<Material[]>(materialUrl + '?limit=20' + (materialBefore ? '&before_id=' + materialBefore : '')),
  })

  function report(error: unknown) {
    if (error instanceof VisitorApiError && error.status === 401) expire()
    void message.error((error as Error).message)
  }

  async function changeBooking(eventId: number, cancel: boolean) {
    setBusy(eventId)
    try {
      await visitorApi(activityUrl + '/' + eventId + '/reservation', token, cancel ? 'DELETE' : 'POST')
      setBookingBefore(undefined)
      void message.success(cancel ? '预约已取消' : '预约成功')
    } catch (error) {
      report(error)
    } finally {
      await cache.invalidateQueries({queryKey: ['visitor']})
      setBusy(undefined)
    }
  }

  async function upload(form: HTMLFormElement) {
    const payload = new FormData(form)
    const file = payload.get('file')
    if (!(file instanceof File) || !file.name) payload.delete('file')
    if (file instanceof File && file.size > 10 * 1024 * 1024) {
      void message.error('文件大小不能超过 10 MB')
      return
    }
    setUploading(true)
    try {
      await visitorApi(materialUrl, token, 'POST', payload)
      form.reset()
      setMaterialBefore(undefined)
      await cache.invalidateQueries({queryKey: ['visitor', 'materials']})
      void message.success('资料已提交')
    } catch (error) {
      report(error)
    } finally {
      setUploading(false)
    }
  }

  return <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
    {key: 'guide', label: '服务指引', children: <>
      <WebsiteAssistant title="登录客服" ask={query => visitorApi<{answer: string}>('/api/cs/visitor/chat', token, 'POST', {query}).catch(error => {
        if (error instanceof VisitorApiError && error.status === 401) expire()
        throw error
      })}/>
      <WebsiteGuide topics={publicTopics} open={setActiveTab}/>
    </>},
    {key: 'events', label: '活动预约', children: <>
      <VisitorError error={activities.error}/>
      <List loading={activities.isLoading} dataSource={activities.data || []} locale={{emptyText: '暂无即将开始的活动'}}
        renderItem={event => {
          const booked = event.reservation_status === 'registered'
          const attended = event.reservation_status === 'attended'
          const seats = (event.max_participants ?? 0) - event.current_participants
          return <List.Item actions={[<Button key="booking" type={booked ? 'default' : 'primary'}
            loading={busy === event.id} disabled={busy !== undefined || attended || (!booked && seats <= 0)}
            onClick={() => void changeBooking(event.id, booked)}>
            {attended ? '已签到' : booked ? '取消预约' : seats <= 0 ? '名额已满' : '预约'}
          </Button>]}>
            <List.Item.Meta title={event.event_name} description={<>
              <p>{displayTime(event.start_time)}{event.end_time && " – " + displayTime(event.end_time)}{event.location && " · " + event.location}</p>
              {event.description && <p>{event.description}</p>}
              <Tag>剩余 {seats} 个名额</Tag>
            </>}/>
          </List.Item>
        }}/>
      <Space>
        <Button disabled={offset === 0 || activities.isFetching} onClick={() => setOffset(value => value - 20)}>上一页</Button>
        <Button disabled={activities.data?.length !== 20 || activities.isFetching} onClick={() => setOffset(value => value + 20)}>下一页</Button>
      </Space>
    </>},
    {key: 'bookings', label: '我的预约', children: <>
      <VisitorError error={bookings.error}/>
      <List loading={bookings.isLoading} dataSource={bookings.data || []} locale={{emptyText: '暂无预约'}}
        renderItem={({event, reservation}) => <List.Item actions={reservation.status === 'registered' ? [
          <Button key="cancel" disabled={busy !== undefined} onClick={() => void changeBooking(event.id, true)}>取消预约</Button>,
        ] : undefined}>
          <List.Item.Meta title={event.event_name} description={displayTime(event.start_time) + ' · ' + event.location}/>
          <Tag>{statusNames[reservation.status]}</Tag>
        </List.Item>}/>
      <Space>
        <Button disabled={bookingBefore === undefined} onClick={() => setBookingBefore(undefined)}>返回最新</Button>
        <Button disabled={bookings.data?.length !== 20}
          onClick={() => setBookingBefore(bookings.data?.at(-1)?.reservation.id)}>查看更多</Button>
      </Space>
    </>},
    {key: 'materials', label: '材料提交', children: <>
      <form className="visitor-upload" onSubmit={event => {event.preventDefault(); void upload(event.currentTarget)}}>
        <Typography.Paragraph>可以先提交已有资料。支持 TXT、CSV、PDF、XLS、XLSX，每次一个文件，最多 10 MB。</Typography.Paragraph>
        <Typography.Paragraph type="secondary">可以先提交已有资料，顾问联系后会确认正式清单并补录。</Typography.Paragraph>
      <ul>
        <li>新加坡国际本硕升学计划：先说明目标升学路径、当前学历和在读或毕业情况。已有成绩单、学历或在读证明可一并提交。</li>
        <li>中德精英人才共建计划：先说明学历、目标职业方向和德语水平。已有学历证明或德语成绩可一并提交。</li>
      </ul>
        <label htmlFor="visitor-notes">资料说明</label>
        <Input.TextArea id="visitor-notes" name="raw_content" rows={3} maxLength={20000}/>
        <label htmlFor="visitor-file">选择附件</label>
        <input id="visitor-file" name="file" type="file" accept=".txt,.csv,.pdf,.xls,.xlsx"/>
        <Button type="primary" htmlType="submit" loading={uploading}>提交材料</Button>
      </form>
      <VisitorError error={materials.error}/>
      <List loading={materials.isLoading} dataSource={materials.data || []} locale={{emptyText: '暂无提交'}}
        renderItem={row => <List.Item>
          <List.Item.Meta title={row.file_name || '文字资料'} description={displayTime(row.submitted_at)}/>
          <Tag>{statusNames[row.status]}</Tag>
        </List.Item>}/>
      <Space>
        <Button disabled={materialBefore === undefined} onClick={() => setMaterialBefore(undefined)}>返回最新</Button>
        <Button disabled={materials.data?.length !== 20} onClick={() => setMaterialBefore(materials.data?.at(-1)?.source_id)}>查看更多</Button>
      </Space>
    </>},
    {key: 'courses', label: '课程与项目', children: <WebsiteCourses request={load}/>},
    {key: 'policies', label: '留学政策', children: <WebsitePolicies request={load}/>},
    {key: 'video', label: '讲座视频', children: <Card id="lecture-video" title="讲座回看">
      <Tag>待开放</Tag> <a href="#lecture-video">讲座视频占位链接</a>
    </Card>},
  ]}/>
}

function VisitorError({error}: {error: Error | null}) {
  return error && <Alert type="error" showIcon title={error.message}/>
}
