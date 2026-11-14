import {useEffect, useState} from 'react'
import {Navigate, useLocation, useNavigate} from 'react-router-dom'
import {Student} from './Student'
import {WebsiteCourses} from './WebsiteCourses'
import {WebsitePolicies} from './WebsitePolicies'
import {WebsiteGuide, type GuideTopic} from './WebsiteGuide'
import {WebsiteAssistant} from './WebsiteAssistant'
import {publicWebsiteContentPath, websiteContentQueryKey, type WebsiteSection} from '../lib/websiteContent'
import {Alert, App, Button, Card, Form, Input, List, Space, Tabs, Tag, Typography} from 'antd'
import {ArrowRightOutlined} from '@ant-design/icons'
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


/* ---------- 首屏轮播：内置矢量插画，纯展示，无接口、无外部图片依赖 ---------- */
const heroSlides = [
  {
    key: 'sg', tag: '升学路径', title: '新加坡国际本硕升学',
    desc: '面向不同学历阶段的升学规划与就业衔接',
    art: (
      <svg viewBox="0 0 440 320" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <rect width="440" height="320" fill="#0A4A44" />
        <circle cx="350" cy="72" r="44" fill="#7EE0CB" opacity=".14" />
        <circle cx="350" cy="72" r="25" fill="#7EE0CB" opacity=".22" />
        <g fill="#FFFFFF" opacity=".10">
          <rect x="18" y="156" width="46" height="114" rx="3" />
          <rect x="72" y="124" width="38" height="146" rx="3" />
          <rect x="118" y="170" width="54" height="100" rx="3" />
          <rect x="180" y="100" width="34" height="170" rx="3" />
          <rect x="222" y="100" width="34" height="170" rx="3" />
          <rect x="264" y="100" width="34" height="170" rx="3" />
          <rect x="306" y="146" width="42" height="124" rx="3" />
          <rect x="356" y="172" width="60" height="98" rx="3" />
        </g>
        <path d="M174 86h132l-10 14H184z" fill="#7EE0CB" opacity=".55" />
        <g stroke="#7EE0CB" strokeWidth="1" opacity=".32">
          <line x1="197" y1="112" x2="197" y2="270" />
          <line x1="239" y1="112" x2="239" y2="270" />
          <line x1="281" y1="112" x2="281" y2="270" />
        </g>
        <rect y="270" width="440" height="50" fill="#062F2C" opacity=".6" />
        <g stroke="#7EE0CB" strokeWidth="1" opacity=".20">
          <line x1="0" y1="284" x2="440" y2="284" />
          <line x1="0" y1="300" x2="440" y2="300" />
          <line x1="0" y1="314" x2="440" y2="314" />
        </g>
      </svg>
    ),
  },
  {
    key: 'de', tag: '职业培训', title: '中德精英人才共建计划',
    desc: '双元制培训、语言准备与企业岗位匹配',
    art: (
      <svg viewBox="0 0 440 320" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <rect width="440" height="320" fill="#0C4B48" />
        <circle cx="168" cy="142" r="86" fill="none" stroke="#7EE0CB" strokeWidth="16" strokeDasharray="20 14" opacity=".32" />
        <circle cx="168" cy="142" r="54" fill="none" stroke="#7EE0CB" strokeWidth="2" opacity=".55" />
        <circle cx="168" cy="142" r="18" fill="#7EE0CB" opacity=".45" />
        <circle cx="316" cy="214" r="46" fill="none" stroke="#7EE0CB" strokeWidth="10" strokeDasharray="12 10" opacity=".28" />
        <g fill="#FFFFFF" opacity=".09">
          <rect x="252" y="96" width="70" height="112" rx="4" />
          <rect x="330" y="128" width="56" height="80" rx="4" />
          <rect x="392" y="152" width="40" height="56" rx="4" />
        </g>
        <g stroke="#7EE0CB" strokeWidth="1.5" opacity=".40">
          <line x1="252" y1="86" x2="252" y2="96" />
          <line x1="330" y1="112" x2="330" y2="128" />
          <path d="M230 142h74" opacity=".5" />
        </g>
        <g fill="#7EE0CB" opacity=".30">
          <circle cx="64" cy="62" r="4" /><circle cx="392" cy="62" r="4" />
          <circle cx="64" cy="258" r="4" /><circle cx="392" cy="258" r="4" />
        </g>
        <rect y="270" width="440" height="50" fill="#062F2C" opacity=".6" />
      </svg>
    ),
  },
  {
    key: 'talk', tag: '线下活动', title: '讲座预约与顾问咨询',
    desc: '查看场次与名额，提交材料并由顾问跟进',
    art: (
      <svg viewBox="0 0 440 320" preserveAspectRatio="xMidYMid slice" aria-hidden="true">
        <rect width="440" height="320" fill="#0A4843" />
        <rect x="58" y="42" width="324" height="158" rx="10" fill="#FFFFFF" opacity=".07" />
        <rect x="58" y="42" width="324" height="158" rx="10" fill="none" stroke="#7EE0CB" strokeWidth="1.5" opacity=".35" />
        <rect x="88" y="72" width="170" height="12" rx="6" fill="#7EE0CB" opacity=".50" />
        <rect x="88" y="98" width="230" height="8" rx="4" fill="#FFFFFF" opacity=".18" />
        <rect x="88" y="118" width="196" height="8" rx="4" fill="#FFFFFF" opacity=".14" />
        <rect x="88" y="138" width="214" height="8" rx="4" fill="#FFFFFF" opacity=".12" />
        <rect x="44" y="212" width="46" height="26" rx="5" fill="#FFFFFF" opacity=".12" />
        <rect x="106" y="212" width="46" height="26" rx="5" fill="#FFFFFF" opacity=".12" />
        <rect x="168" y="212" width="46" height="26" rx="5" fill="#FFFFFF" opacity=".12" />
        <rect x="230" y="212" width="46" height="26" rx="5" fill="#FFFFFF" opacity=".12" />
        <rect x="292" y="212" width="46" height="26" rx="5" fill="#FFFFFF" opacity=".12" />
        <rect x="354" y="212" width="46" height="26" rx="5" fill="#FFFFFF" opacity=".12" />
        <rect x="44" y="252" width="46" height="26" rx="5" fill="#FFFFFF" opacity=".08" />
        <rect x="106" y="252" width="46" height="26" rx="5" fill="#FFFFFF" opacity=".08" />
        <rect x="168" y="252" width="46" height="26" rx="5" fill="#FFFFFF" opacity=".08" />
        <rect x="230" y="252" width="46" height="26" rx="5" fill="#FFFFFF" opacity=".08" />
        <rect x="292" y="252" width="46" height="26" rx="5" fill="#FFFFFF" opacity=".08" />
        <rect x="354" y="252" width="46" height="26" rx="5" fill="#FFFFFF" opacity=".08" />
        <circle cx="330" cy="176" r="13" fill="#7EE0CB" opacity=".45" />
        <path d="M310 200h40l-6-14h-28z" fill="#7EE0CB" opacity=".35" />
      </svg>
    ),
  },
]

function HeroCarousel() {
  const [active, setActive] = useState(0)
  useEffect(() => {
    const timer = window.setInterval(() => setActive(value => (value + 1) % heroSlides.length), 5000)
    return () => window.clearInterval(timer)
  }, [])
  return <div className="hero-carousel" role="region" aria-label="项目展示轮播">
    {heroSlides.map((slide, index) => <div key={slide.key}
      className={'hero-slide' + (index === active ? ' is-active' : '')}
      aria-hidden={index !== active}>
      <div className="hero-slide-art">{slide.art}</div>
      <div className="hero-slide-shade" />
      <div className="hero-slide-copy">
        <span className="hero-slide-tag">{slide.tag}</span>
        <div className="hero-slide-title">{slide.title}</div>
        <div className="hero-slide-desc">{slide.desc}</div>
      </div>
    </div>)}
    <div className="hero-carousel-counter">{String(active + 1).padStart(2, "0")} / {String(heroSlides.length).padStart(2, "0")}</div>
    <div className="hero-carousel-dots">
      {heroSlides.map((slide, index) => <button key={slide.key} type="button"
        className={'hero-dot' + (index === active ? ' is-active' : '')}
        aria-label={'切换到第 ' + (index + 1) + ' 张：' + slide.title}
        aria-current={index === active}
        onClick={() => setActive(index)} />)}
    </div>
  </div>
}

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
  const sections = useQuery({
    queryKey: websiteContentQueryKey, enabled: identity.data?.account_type !== 'student',
    queryFn: () => visitorApi<WebsiteSection[]>(publicWebsiteContentPath, ''),
  })
  const hasContent = !!sections.data
  useEffect(() => {
    if (hasContent && current.hash) document.getElementById(current.hash.slice(1))?.scrollIntoView()
  }, [hasContent, current.hash])
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
      <div className="visitor-header-left">
        <a href="/website" className="visitor-logo">粤教教育服务</a>
        <nav className="visitor-nav" aria-label="官网导航">
          {sections.data?.map(section => <a key={section.id} href={'#' + section.anchor}>{section.title}</a>)}
          <a href="#visitor-services">游客服务</a>
        </nav>
      </div>
      <div className="visitor-header-actions">
        {token ? <>
          <Button href="#visitor-services">查看活动和资料</Button>
          <Button type="primary" loading={authBusy} onClick={() => void signOut()}>退出登录</Button>
        </> : <Button type="primary" href="#visitor-services">登录 / 注册</Button>}
      </div>
    </header>

    <section className="visitor-intro">
      <div className="visitor-intro-inner">
        <div className="visitor-intro-copy">
          <span className="intro-eyebrow">粤教教育服务 · 留学与升学</span>
          <Typography.Title>了解留学项目，<br />预约线下讲座</Typography.Title>
          <Typography.Paragraph>查看新加坡和德国项目，向顾问提交已有材料，跟踪处理进度。</Typography.Paragraph>
          {sections.data?.some(section => section.anchor === 'programs') &&
            <a className="intro-text-link" href="#programs">了解留学项目 <ArrowRightOutlined /></a>}
          <div className="intro-trust">新加坡升学 · 德国双元制 · 顾问一对一跟进</div>
        </div>
        <HeroCarousel />
      </div>
    </section>

    {sections.isError && <section className="visitor-section">
      <Alert type="warning" showIcon title="官网栏目暂时无法加载" action={
        <Button size="small" onClick={() => void sections.refetch()}>重试</Button>
      }/>
    </section>}
    {sections.data?.map(section => <section key={section.id} id={section.anchor} className="visitor-section">
      <Typography.Title level={2}>{section.title}</Typography.Title>
      <div className="visitor-programs">
        {section.cards.map(card => <Card key={card.id} title={card.title}>
          <div style={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{card.content}</div>
        </Card>)}
      </div>
    </section>)}

    <section id="visitor-services" className="visitor-section">
      <Typography.Title level={2}>游客服务</Typography.Title>
      {!token && <>
        <Alert
          type="info"
          showIcon
          style={{marginBottom: 16}}
          title="学生助手需要登录"
          description="请假、查进度、投诉、对话记忆都在登录后的学生页。请先用官网账号登录；未开通学生权限时只会看到游客服务。"
        />
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
    <footer className="visitor-footer">
      <div className="visitor-footer-inner">
        <div>
          <strong>粤教教育服务</strong>
          <p>新加坡升学 · 德国职业培训 · 数字化顾问服务</p>
        </div>
        <div className="visitor-footer-links">
          {sections.data?.map(section => <a key={section.id} href={'#' + section.anchor}>{section.title}</a>)}
          <a href="#visitor-services">游客服务</a>
        </div>
        <span>© 2026 粤教教育服务 · 具体安排以顾问确认的信息为准</span>
      </div>
    </footer>
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
      <WebsiteAssistant
        title="登录客服"
        hints={['活动怎么预约', '材料怎么交', '有哪些留学项目']}
        intro="这里是游客客服。请假、投诉、学籍进度请到学生页使用学生助手。"
        ask={(query) => visitorApi<{answer: string}>('/api/cs/visitor/chat', token, 'POST', {query}).catch(error => {
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
