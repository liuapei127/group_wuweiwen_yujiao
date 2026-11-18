import {useEffect, useState} from 'react'
import {Link, Navigate, useLocation, useNavigate} from 'react-router-dom'
import {Student} from './Student'
import {WebsiteCourses} from './WebsiteCourses'
import {WebsitePolicies} from './WebsitePolicies'
import {WebsiteGuide, type GuideTopic} from './WebsiteGuide'
import {WebsiteAssistant, type AssistantTurn} from './WebsiteAssistant'
import {WebsiteAccountMenu, type WebsiteProfile} from './WebsiteAccountMenu'
import {WebsiteCustomerProfile} from './CustomerWorkspace'
import {StudentProfile} from './StudentProfile'
import {publicWebsiteContentPath, websiteContentQueryKey, type WebsiteSection} from '../lib/websiteContent'
import {Alert, App, Button, Card, Form, Input, List, Modal, Space, Tabs, Tag, Typography} from 'antd'
import {ArrowLeftOutlined, ArrowRightOutlined, MessageOutlined} from '@ant-design/icons'
import {useQuery, useQueryClient} from '@tanstack/react-query'
import {mobileNumberMessage, mobileNumberPattern} from '../lib/mobile'
import {readChatStream} from '../lib/chat-stream'
import {newPasswordRules} from '../lib/password'
import {PasswordChangeDialog} from '../components/PasswordChangeDialog'

type CustomerChatReply = {answer: string; session_id?: string; reservation_changed?: boolean}

function customerChatBody(query: string, sessionId?: string, history?: AssistantTurn[]) {
  const start = sessionId ? {query, session_id: sessionId} : {query, start_session: true}
  return history ? {...start, history: history.slice(-8).map(({role, content}) => ({role, content: content.slice(0, 500)}))} : start
}

type Activity = {
  id: number; event_name: string; description?: string; location: string | null; start_time: string; end_time: string | null
  current_participants: number; max_participants: number | null; reservation_status?: string
}
type Booking = {event: Activity; reservation: {id: number; status: string}}
type Material = {source_id: number; file_name: string | null; submitted_at: string; status: string}
type WebsiteIdentity = {account_type: 'visitor' | 'student'}
type Credentials = {username: string; password: string; nickname?: string}

const publicTopics: GuideTopic[] = [
  {key: 'events', label: '活动预约', keywords: ['活动', '预约', '讲座'], answer: '注册并登录后可查看线下讲座时间和名额，也可在线取消预约。'},
  {key: 'materials', label: '材料提交', keywords: ['材料', '文件', '上传', '资料'], answer: '可以先提交已有材料，顾问会联系确认其他资料。'},
  {key: 'courses', label: '课程与项目', keywords: ['课程', '项目', '德国', '新加坡'], answer: '官网介绍新加坡升学和德国职业培训项目，登录后可查询已发布的课程与项目。'},
  {key: 'policies', label: '留学政策', keywords: ['政策', '签证', '准证'], answer: '登录后可按国家查看政策及官方办理入口。'},
]


/* 官网栏目接口不可用时用静态内容兜底，保证导航与页面始终完整 */
const fallbackSections: WebsiteSection[] = [
  {id: -1, anchor: 'about', title: '关于粤教', cards: [
    {id: -11, title: '留学与升学服务', content: '了解新加坡升学和德国职业培训项目。注册后可预约讲座、提交手头已有的材料，由顾问跟进。'},
    {id: -12, title: '数字化服务', content: '官网集中提供政策、课程和活动查询。顾问工作台汇总材料和跟进记录，方便顾问核对资料和补录。'},
  ]},
  {id: -2, anchor: 'programs', title: '留学项目', cards: [
    {id: -21, title: '新加坡国际本硕升学计划', content: '提供面向不同学历阶段的升学路径，以及酒店和航空方向的就业项目。'},
    {id: -22, title: '中德精英人才共建计划', content: '了解德国双元制职业培训和企业匹配流程，项目包含语言学习与岗位准备。'},
  ]},
  {id: -3, anchor: 'services', title: '我们的服务', cards: [
    {id: -31, title: '一对一顾问咨询', content: '从预算、学制到专业方向，顾问会与你一起确认适合的项目与院校范围。'},
    {id: -32, title: '材料与进度跟进', content: '注册后可提交已有材料、预约线下讲座，并随时查看处理进度。'},
  ]},
]

/* ---------- 首屏：全幅照片背景轮播 ---------- */
const heroSlides = [
  {key: 'graduate', image: '/hero-1.webp', label: '毕业与升学'},
  {key: 'campus', image: '/hero-2.webp', label: '国际校园'},
  {key: 'consult', image: '/hero-3.webp', label: '顾问咨询'},
]

/* 栏目专属背景图：按 anchor 优先匹配；接口返回自定义栏目时按顺序兜底 */
const sectionArtList = ['/section-about.webp', '/section-programs.webp', '/section-life.webp']
const sectionArtByAnchor: Record<string, string> = {
  about: sectionArtList[0],
  programs: sectionArtList[1],
  life: sectionArtList[2],
  living: sectionArtList[2],
  services: sectionArtList[2],
}
const artFor = (anchor: string, index: number) => sectionArtByAnchor[anchor] ?? sectionArtList[index % sectionArtList.length]

function HeroBanner({onOpenAssistant}: {onOpenAssistant: () => void}) {
  const [active, setActive] = useState(0)
  useEffect(() => {
    const timer = window.setInterval(() => setActive(value => (value + 1) % heroSlides.length), 6000)
    return () => window.clearInterval(timer)
  }, [])
  // 预取下一张，轮播切换不闪白；同一时刻只加载当前图
  useEffect(() => {
    const next = new Image()
    next.src = heroSlides[(active + 1) % heroSlides.length].image
  }, [active])
  return <section className="visitor-intro">
    <div className="hero-backdrop" aria-hidden="true">
      <img key={heroSlides[active].key} src={heroSlides[active].image} alt="" />
    </div>
    <div className="hero-overlay" aria-hidden="true" />
    <div className="visitor-intro-inner">
      <div className="hero-copy">
        <span className="intro-eyebrow">YOUR NEXT CHAPTER STARTS HERE</span>
        <h1 className="hero-title">
          <span className="hero-title-main">粤教国际教育</span>
          <span className="hero-title-accent">留学与升学服务</span>
        </h1>
        <p className="hero-desc">从今天的选择，到世界的舞台。<br />与你一起，找到适合自己的国际升学之路。</p>
        <div className="hero-actions">
          <Button type="primary" className="hero-cta-primary" href="#programs">
            探索留学项目 <ArrowRightOutlined />
          </Button>
          <Button className="hero-cta-ghost" onClick={onOpenAssistant}>
            与升学助手聊聊 <MessageOutlined />
          </Button>
        </div>
        <div className="hero-carousel-nav">
          {heroSlides.map((slide, index) => <button key={slide.key} type="button"
            className={'hero-dot' + (index === active ? ' is-active' : '')}
            aria-label={'切换到第 ' + (index + 1) + ' 张：' + slide.label}
            aria-current={index === active}
            onClick={() => setActive(index)} />)}
          <span className="hero-carousel-count">{String(active + 1).padStart(2, "0")} / {String(heroSlides.length).padStart(2, "0")}</span>
          <span className="hero-carousel-label">{heroSlides[active].label}</span>
        </div>
      </div>
    </div>
  </section>
}

const visitorHome = '/website/visitor'
const visitorServicesPath = visitorHome + '/services'
const customerProfilePath = '/website/profile'
const storageKey = 'yujiao-visitor-token'
const guestChatKey = 'website-customer-chat'
const memberChatKey = 'website-customer-chat-session'

function registeredChatKey(fresh = false) {
  const previous = sessionStorage.getItem(memberChatKey)
  if (previous && !fresh) return previous
  if (previous) sessionStorage.removeItem(previous)
  const key = guestChatKey + ':account:' + crypto.randomUUID()
  sessionStorage.setItem(memberChatKey, key)
  return key
}
const activityUrl = '/api/v1/visitor/events'
const materialUrl = '/api/v1/visitor/materials'
const statusNames: Record<string, string> = {
  registered: '已预约', cancelled: '已取消', attended: '已签到',
  received: '已收到', imported: '已导入', needs_information: '待补充', reviewed: '已研判',
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

async function visitorApi<T>(path: string, token: string, method = 'GET', body?: unknown, onText?: (text: string) => void): Promise<T> {
  const isFile = body instanceof FormData
  let response: Response
  try {
    response = await fetch(path, {
      method,
      headers: {
        ...(token ? {Authorization: 'Bearer ' + token} : {}),
        ...(onText ? {Accept: 'text/event-stream'} : {}),
        ...(body !== undefined && !isFile ? {'Content-Type': 'application/json'} : {}),
      },
      body: isFile ? body : body === undefined ? undefined : JSON.stringify(body),
      signal: AbortSignal.timeout(onText ? 260000 : 30000),
    })
  } catch (error) {
    throw new VisitorApiError(error instanceof DOMException && error.name === 'TimeoutError'
      ? '请求超时，请稍后重试。' : '无法连接服务，请稍后重试。', 0)
  }
  if (response.ok && onText && response.headers.get('content-type')?.includes('text/event-stream')) {
    return readChatStream<T>(response, onText, (message, status) => new VisitorApiError(message, status))
  }
  const result = await response.json().catch(() => null)
  if (!response.ok || result?.code !== 0) {
    const detail = result?.detail || result?.message
    const fallback = response.status >= 500 ? '服务暂时不可用，请稍后重试。'
      : response.ok ? '服务响应异常，请稍后重试。' : '操作未完成，请重试'
    throw new VisitorApiError(Array.isArray(detail)
      ? detail.map(d => d.msg).join('；')
      : typeof detail === 'string' ? detail : fallback, response.status)
  }
  return result.data as T
}

export function Visitor() {
  const [token, setToken] = useState(() => sessionStorage.getItem(storageKey) || '')
  const [chatKey, setChatKey] = useState(() => token ? registeredChatKey() : guestChatKey)
  const current = useLocation()
  const navigate = useNavigate()
  const publicPath = current.pathname.replace(/\/$/, '')
  const isServicesPage = publicPath === visitorServicesPath
  const isProfilePage = publicPath === customerProfilePath
  const legacyServicesLink = (publicPath === '/website' || publicPath === visitorHome) && current.hash === '#visitor-services'
  const returnToServices = current.state?.returnTo === visitorServicesPath
  const returnToProfile = current.state?.returnTo === customerProfilePath
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
  useEffect(() => {
    if (!current.hash) window.scrollTo({top: 0, behavior: 'instant'})
  }, [publicPath, current.hash])
  const [authOpen, setAuthOpen] = useState(false)
  const [register, setRegister] = useState(false)
  const [assistantOpen, setAssistantOpen] = useState(false)
  const [authBusy, setAuthBusy] = useState(false)
  const [changingPassword, setChangingPassword] = useState(false)
  const {message} = App.useApp()
  const cache = useQueryClient()

  function clearSession() {
    sessionStorage.removeItem(storageKey)
    if (chatKey !== guestChatKey) sessionStorage.removeItem(chatKey)
    sessionStorage.removeItem(memberChatKey)
    setChatKey(guestChatKey)
    setChangingPassword(false)
    setToken('')
    void cache.cancelQueries({queryKey: ['visitor']})
    cache.removeQueries({queryKey: ['visitor']})
    void navigate('/website', {replace: true})
  }

  function openLogin() {
    setRegister(false)
    setAuthOpen(true)
  }

  function closeLogin() {
    setAuthOpen(false)
    if (returnToServices || returnToProfile) void navigate('/website', {replace: true})
  }

  async function signIn({username, password, nickname}: Credentials) {
    setAuthBusy(true)
    try {
      const result = await visitorApi<WebsiteIdentity & {access_token: string}>(
        '/api/v1/visitors/' + (register ? 'register' : 'login'), '', 'POST',
        {username, password, ...(register ? {nickname: nickname?.trim()} : {})},
      )
      sessionStorage.setItem(storageKey, result.access_token)
      setChatKey(registeredChatKey(true))
      message.destroy('website-auth')
      cache.setQueryData(['visitor', 'identity', result.access_token], {account_type: result.account_type})
      setAuthOpen(false)
      setToken(result.access_token)
      const destination = returnToServices ? visitorServicesPath : visitorHome
      void navigate(returnToProfile ? customerProfilePath : result.account_type === 'student' ? '/website/student' : destination, {replace: true})
    } catch (error) {
      void message.error({key: 'website-auth', content: (error as Error).message})
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
  if (!token && (publicPath !== '/website' || legacyServicesLink)) {
    const state = isProfilePage ? {returnTo: customerProfilePath} : isServicesPage || legacyServicesLink ? {returnTo: visitorServicesPath} : undefined
    return <Navigate to="/website" state={state} replace/>
  }
  if (token && identity.error) {
    return <main className="visitor-site"><section className="visitor-section">
      <Alert type="error" showIcon title={identityExpired ? '官网登录已失效' : identity.error.message}/>
      <Space style={{marginTop: 12}}>
        <Button onClick={() => {clearSession(); openLogin()}}>返回登录</Button>
        {!identityExpired && <Button onClick={() => void identity.refetch()}>重试</Button>}
      </Space>
    </section></main>
  }
  const accountType = identity.data?.account_type
  if (token && accountType === 'student' && !isProfilePage && publicPath !== '/website/student') {
    return <Navigate to="/website/student" replace/>
  }
  if (token && accountType === 'visitor') {
    if (legacyServicesLink) return <Navigate to={visitorServicesPath} replace/>
    if (!isServicesPage && !isProfilePage && publicPath !== visitorHome) {
      return <Navigate to={{pathname: visitorHome, hash: current.hash}} replace/>
    }
  }
  if (token && !accountType) return <main className="visitor-site"><section className="visitor-section">正在核对官网身份…</section></main>
  const expire = () => {
    if (sessionStorage.getItem(storageKey) === token) clearSession()
  }
  const changePassword = token && changingPassword && <PasswordChangeDialog
    submit={passwords => visitorApi('/api/v1/visitors/password', token, 'POST', passwords).catch((error: unknown) => {
      if (error instanceof VisitorApiError && error.status === 401) {
        expire()
        openLogin()
      }
      throw error
    })}
    onClose={() => setChangingPassword(false)}
    onChanged={() => {clearSession(); openLogin()}}/>
  const accountActions = token && <WebsiteAccountMenu key={token} token={token} signingOut={authBusy}
    onViewCustomer={() => void navigate(customerProfilePath)}
    request={<T,>(path: string, method?: string, body?: unknown) => visitorApi<T>(path, token, method, body)
      .catch((error: unknown) => {
        if (error instanceof VisitorApiError && error.status === 401) expire()
        throw error
      })}
    onChangePassword={() => setChangingPassword(true)}
    onSignOut={() => void signOut()}/>

  if (token && isProfilePage && !accountType) {
    return <main className="visitor-site"><Typography.Paragraph>正在确认账号身份…</Typography.Paragraph></main>
  }
  if (token && isProfilePage) {
    const back = () => void navigate(accountType === 'student' ? '/website/student' : visitorHome)
    return <main className="visitor-site visitor-site--services">
      <header className="visitor-header visitor-header--public visitor-header--services">
        <div className="visitor-header-left"><Link className="visitor-logo" to={visitorHome}>粤教教育服务</Link></div>
        <div className="visitor-header-actions">{accountActions}</div>
      </header>
      {accountType === 'student' ? <StudentProfile token={token} back={back}
        request={<T,>(path: string, method?: string, body?: unknown) => visitorApi<T>(path, token, method, body)
          .catch((error: unknown) => {
            if (error instanceof VisitorApiError && error.status === 401) expire()
            throw error
          })}/> : <WebsiteCustomerProfile token={token} back={back}
        request={<T,>(path: string, method?: string, body?: unknown, onText?: (text: string) => void) => visitorApi<T>(path, token, method, body, onText)
          .catch((error: unknown) => {
            if (error instanceof VisitorApiError && error.status === 401) expire()
            throw error
          })}/>}
      {changePassword}
    </main>
  }

  if (token && accountType === 'student') {
    const request = <T,>(path: string, method?: string, body?: unknown, onText?: (text: string) => void) =>
      visitorApi<T>(path, token, method, body, onText)
      .catch((error: unknown) => {
        if (error instanceof VisitorApiError && (error.status === 401 || error.status === 403)) void identity.refetch()
        throw error
      })
    return <main className="visitor-site visitor-site--student">
      <header className="visitor-header visitor-header--student">
        <div className="visitor-header-left">
          <Link to="/website" className="visitor-logo">粤教教育服务</Link>
          <span className="visitor-header-tag">学生服务中心</span>
        </div>
        <div className="visitor-header-actions">
          <Button onClick={() => void navigate(customerProfilePath)}>我的学籍</Button>{accountActions}
        </div>
      </header>
      <Student request={request} accountRecords={<VisitorServices token={token} expire={expire} chatKey={chatKey} showAssistant/>}/>
      {changePassword}
    </main>
  }
  return <main className={isServicesPage ? 'visitor-site visitor-site--services' : 'visitor-site'}>
    <header className={'visitor-header visitor-header--public' + (isServicesPage ? ' visitor-header--services' : '')}>
      <div className="visitor-header-left">
        <Link to={token ? visitorHome : "/website"} className="visitor-logo">粤教教育服务</Link>
        {!isServicesPage && <nav className="visitor-nav" aria-label="官网导航">
          {(sections.data?.length ? sections.data : fallbackSections).map(section => <a key={section.id} href={'#' + section.anchor}>{section.title}</a>)}
        </nav>}
      </div>
      <div className="visitor-header-actions">
        {token ? <>
          {isServicesPage
            ? <Button icon={<ArrowLeftOutlined/>} onClick={() => void navigate(visitorHome)}>返回官网</Button>
            : <Button onClick={() => void navigate(visitorServicesPath)}>查看活动和资料</Button>}
          {accountActions}
        </> : <Button type="primary" aria-haspopup="dialog" onClick={openLogin}>登录</Button>}
      </div>
    </header>

    {isServicesPage ? <section className="visitor-section visitor-services-page" aria-label="游客服务">
      <VisitorServices token={token} expire={expire} vertical/>
    </section> : <>
      <HeroBanner onOpenAssistant={() => setAssistantOpen(true)} />

      {sections.isError && <p className="visitor-content-note">
        栏目内容暂以默认版本展示。<button type="button" onClick={() => void sections.refetch()}>重新加载</button>
      </p>}
      {(sections.data?.length ? sections.data : fallbackSections).map((section, sectionIndex) => <section key={section.id} id={section.anchor} className="visitor-section">
        <div className="visitor-section-art" aria-hidden="true" style={{backgroundImage: `url(${artFor(section.anchor, sectionIndex)})`}}/>
        <Typography.Title level={2}>{section.title}</Typography.Title>
        <div className="visitor-programs">
          {section.cards.map(card => <Card key={card.id} title={card.title}>
            <div style={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{card.content}</div>
          </Card>)}
        </div>
      </section>)}

    </>}

    <Modal
      className="visitor-login"
      title={register ? '注册游客账号' : '官网登录'}
      open={!token && (authOpen || returnToServices || returnToProfile)}
      onCancel={closeLogin}
      footer={null}
      centered
      width={440}
      destroyOnHidden
      closable={!authBusy}
      keyboard={!authBusy}
      mask={{closable: !authBusy}}
    >
      <Form<Credentials> key={String(register)} name="website-auth" layout="vertical" onFinish={v => void signIn(v)}>
        {register && <Form.Item label="昵称" name="nickname"
          rules={[{required: true, whitespace: true, message: '请输入昵称'}]}>
          <Input autoComplete="nickname" maxLength={64}/>
        </Form.Item>}
        <Form.Item label="手机号" name="username" rules={[
          {required: true, message: '请输入手机号'},
          {pattern: mobileNumberPattern, message: mobileNumberMessage},
        ]}>
          <Input autoComplete="username" inputMode="tel" maxLength={11}/>
        </Form.Item>
        <Form.Item label="密码" name="password"
          rules={register ? newPasswordRules() : [{required: true, message: '请输入密码'}]}>
          <Input.Password autoComplete={register ? 'new-password' : 'current-password'} maxLength={128}/>
        </Form.Item>
        <div className="visitor-login-actions">
          <Button type="primary" htmlType="submit" loading={authBusy}>{register ? '注册' : '登录'}</Button>
          <Button type="link" disabled={authBusy} onClick={() => setRegister(value => !value)}>
            {register ? '已有账号，去登录' : '注册游客账号'}
          </Button>
        </div>
      </Form>
    </Modal>
    {changePassword}

    {!isServicesPage && <footer className="visitor-footer">
      <div className="visitor-footer-inner">
        <div>
          <strong>粤教教育服务</strong>
          <p>新加坡升学 · 德国职业培训 · 数字化顾问服务</p>
        </div>
        <div className="visitor-footer-links">
          {(sections.data?.length ? sections.data : fallbackSections).map(section => <a key={section.id} href={'#' + section.anchor}>{section.title}</a>)}
        </div>
        <span>© 2026 粤教教育服务 · 具体安排以顾问确认的信息为准</span>
      </div>
    </footer>}
    <WebsiteAssistant
      key={chatKey}
      title="粤教升学助手"
      hints={['德国项目', '新加坡项目', '如何报名活动']}
      intro={'你好，我是粤教升学助手。选国家和院校，一般可以按三步走：先看预算与学制，再看专业方向和院校匹配，最后确认签证与就业政策。\n\n如果有比较心仪的院校，或者更看重预算、学制还是专业排名？告诉我一个侧重点，我就能帮你把范围收窄。'}
      open={assistantOpen}
      onOpenChange={setAssistantOpen}
      chatStorageKey={chatKey}
      ask={async (query, history, sessionId, onText) => {
        const path = token ? '/api/cs/visitor/chat' : '/api/cs/chat'
        const send = (id?: string) => visitorApi<CustomerChatReply>(path, token, 'POST', customerChatBody(query, id, history), onText)
        try {
          const reply = await send(sessionId).catch(error => {
            if (error instanceof VisitorApiError && error.status === 404 && sessionId) return send()
            throw error
          })
          if (reply.reservation_changed) {
            void cache.invalidateQueries({queryKey: ['visitor', 'activities']})
            void cache.invalidateQueries({queryKey: ['visitor', 'bookings']})
          }
          if (token) void cache.invalidateQueries({queryKey: ['visitor', 'crm-profile', token]})
          return reply
        } catch (error) {
          if (error instanceof VisitorApiError && error.status === 401 && token) {
            expire()
            throw error
          }
          const text = query.toLowerCase()
          const hit = publicTopics.find(topic => topic.keywords.some(word => text.includes(word)))
          return {answer: '（在线客服暂未连接，以下为常见问题指引）\n' + (hit
            ? hit.answer
            : '你可以注册账号后由顾问跟进，或直接问我：活动预约、材料提交、留学项目、留学政策。')}
        }
      }} />
  </main>
}

function VisitorServices({token, expire, chatKey, showAssistant = false, vertical = false}: {
  token: string; expire: () => void; chatKey?: string; showAssistant?: boolean; vertical?: boolean
}) {
  const [activeTab, setActiveTab] = useState('events')
  const [offset, setOffset] = useState(0)
  const [bookingBefore, setBookingBefore] = useState<number>()
  const [materialBefore, setMaterialBefore] = useState<number>()
  const [busy, setBusy] = useState<number>()
  const [bookingEvent, setBookingEvent] = useState<number>()
  const [bookingError, setBookingError] = useState<Error | null>(null)
  const [bookingForm] = Form.useForm<{name: string}>()
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
    enabled: activeTab === 'events',
    staleTime: 0,
    refetchOnWindowFocus: true,
  })
  const profile = useQuery({
    queryKey: ['visitor', 'profile', token],
    queryFn: () => load<WebsiteProfile>('/api/v1/visitors/profile'),
    enabled: bookingEvent !== undefined,
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

  async function changeBooking(eventId: number, cancel: boolean, name?: string) {
    setBusy(eventId)
    setBookingError(null)
    try {
      await visitorApi(activityUrl + '/' + eventId + '/reservation', token, cancel ? 'DELETE' : 'POST',
        name === undefined ? undefined : {name: name.trim()})
      setBookingEvent(undefined)
      setBookingBefore(undefined)
      void message.success(cancel ? '预约已取消' : '预约成功')
    } catch (error) {
      if (!cancel && name === undefined && error instanceof VisitorApiError && error.status === 422) {
        setBookingEvent(eventId)
      } else if (name !== undefined && error instanceof Error && !(error instanceof VisitorApiError && error.status === 401)) {
        setBookingError(error)
      } else {
        report(error)
      }
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

  return <>
    <Modal title="填写姓名后预约" open={bookingEvent !== undefined} centered destroyOnHidden
      okText="确认预约" cancelText="取消" confirmLoading={busy !== undefined}
      closable={busy === undefined} mask={{closable: busy === undefined}} keyboard={busy === undefined}
      cancelButtonProps={{disabled: busy !== undefined}}
      onCancel={() => {if (busy === undefined) setBookingEvent(undefined)}}
      onOk={() => bookingForm.submit()}>
      <VisitorError error={bookingError}/>
      <Form form={bookingForm} name="website-booking" layout="vertical" clearOnDestroy disabled={busy !== undefined}
        onFinish={({name}) => {
          if (bookingEvent !== undefined && busy === undefined) void changeBooking(bookingEvent, false, name)
        }}>
        <Form.Item label="姓名" name="name" rules={[{required: true, whitespace: true, message: '请输入姓名'}]}>
          <Input autoComplete="name" maxLength={64}/>
        </Form.Item>
        {profile.data && <Typography.Paragraph type="secondary">联系方式：{profile.data.contact}</Typography.Paragraph>}
      </Form>
    </Modal>
    <Tabs tabPlacement={vertical ? 'start' : 'top'} className={vertical ? 'visitor-services-tabs' : undefined}
      tabBarGutter={vertical ? 4 : undefined} activeKey={activeTab} onChange={setActiveTab} items={[
    {key: 'guide', label: '服务指引', children: <>
      <WebsiteGuide topics={publicTopics} open={setActiveTab} showSearch={!vertical}/>
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
    {showAssistant && <WebsiteAssistant
      key={chatKey}
      chatStorageKey={chatKey}
      title="登录客服"
      hints={['活动怎么预约', '材料怎么交', '有哪些留学项目']}
      intro="这里是游客客服。请假、投诉、学籍进度请到学生页使用学生助手。"
      ask={async (query, history, sessionId, onText) => {
        const send = (id?: string) => visitorApi<CustomerChatReply>(
          '/api/cs/visitor/chat', token, 'POST', customerChatBody(query, id, history), onText,
        )
        const reply = await send(sessionId).catch(error => {
          if (error instanceof VisitorApiError && error.status === 401) expire()
          if (error instanceof VisitorApiError && error.status === 404 && sessionId) return send()
          throw error
        })
        if (reply.reservation_changed) {
          void cache.invalidateQueries({queryKey: ['visitor', 'activities']})
          void cache.invalidateQueries({queryKey: ['visitor', 'bookings']})
        }
        void cache.invalidateQueries({queryKey: ['visitor', 'crm-profile', token]})
        return reply
      }}/>}
  </>
}

function VisitorError({error}: {error: Error | null}) {
  return error && <Alert type="error" showIcon title={error.message}/>
}
