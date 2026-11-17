import {useEffect, useRef, useState} from 'react'
import {Alert, App, Avatar, Button, Card, Input, Space, Spin, Tag} from 'antd'
import type {TextAreaRef} from 'antd/es/input/TextArea'
import {
  AudioOutlined, CheckOutlined, CloseOutlined, LeftOutlined, MessageOutlined,
  PlusOutlined, RobotOutlined, SearchOutlined, UserOutlined,
} from '@ant-design/icons'
import {useQuery, useQueryClient} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ReportVoiceInput} from '../components/ReportVoiceInput'
import {ErrorNotice, Value} from '../components/shared'
import {api} from '../lib/api'
import './assistant.css'

const labels:Record<string,string>={formal_report:'生成并归档正式报告',lead_create:'录入客户',lead_update:'修改客户',lead_status:'更新客户状态',lead_follow_up:'追加跟进',daily_submit:'提交日报',guide_create:'新增指南',score_create:'录入成绩',score_correct:'更正成绩',leave_approve:'审批请假',ticket_update:'处理工单',todo_create:'新增待办',todo_update:'更新待办'}
const fieldNames:Record<string,string>={report_kind:'报告类型',anchor:'统计日期',customer_name:'客户姓名',contact_info:'联系方式',intended_country:'意向国家',intended_major:'意向专业',lead_id:'客户编号',status:'目标状态',lost_reason:'流失原因',content:'内容',report_date:'日报日期',key_progress:'关键进展',risks:'风险',next_plan:'下一步计划',student_id:'学生编号',course_name:'课程',score:'成绩',semester:'学期',exam_key:'考试标识',expected_version:'当前版本',correction_reason:'更正原因',leave_id:'请假单编号',decision:'审批决定',approval_comment:'审批意见',ticket_id:'工单编号',solution:'解决说明',todo_id:'待办编号',title:'标题',description:'说明',priority:'优先级',due_time:'到期时间',expected_status:'原状态',category:'分类',remark:'备注'}

const conversationsUrl = '/api/v1/ai/assistant/conversations'
const messageLimit = 8000
const dateOptions = {timeZone: 'Asia/Shanghai'} as const
const calendarDate = new Intl.DateTimeFormat('zh-CN', dateOptions)
const calendarDay = new Intl.DateTimeFormat('zh-CN', {...dateOptions, month: 'numeric', day: 'numeric'})
const clock = new Intl.DateTimeFormat('zh-CN', {...dateOptions, hour: '2-digit', minute: '2-digit', hourCycle: 'h23'})

type ChatMessage = {
  id: number
  role: 'user' | 'assistant'
  content: string
  create_time?: string
  metadata?: {http_status?: number; error_status?: number}
}
type PendingAction = {state: 'confirm' | 'id' | 'collect'; intent: string; params?: Record<string, unknown>; field?: string}
type ConversationOverview = {id: string; title: string; version: number; update_time?: string}
type Conversation = ConversationOverview & {messages: ChatMessage[]; pending?: PendingAction}

function chatTime(value?: string) {
  if (!value) return undefined
  const date = new Date(/Z$|[+-]\d{2}:\d{2}$/i.test(value) ? value : value + 'Z')
  return Number.isNaN(date.getTime()) ? undefined : date
}

function timestamp(date: Date, includeClock = false) {
  const day = calendarDay.format(date)
  if (calendarDate.format(date) === calendarDate.format(new Date())) return clock.format(date)
  return includeClock ? day + ' ' + clock.format(date) : day
}

function MessageBubble({mine, content, initials, failed}: {
  mine: boolean; content: string; initials?: string; failed?: boolean
}) {
  return <div className={'assistant-message' + (mine ? ' assistant-message--sent' : '')} aria-label={mine ? '我' : 'ENT 助手'}>
    <Avatar shape="square" size={34} className="assistant-avatar" icon={mine
      ? (initials ? undefined : <UserOutlined/>) : <RobotOutlined/>} aria-hidden="true">
      {mine ? initials : null}
    </Avatar>
    <div className="assistant-message-body">
      <div className="assistant-chat-bubble">{content}</div>
      {failed && <span className="assistant-message-error">请求未完成</span>}
    </div>
  </div>
}

export function Assistant() {
  const {user, can} = useAuth()
  const {message} = App.useApp()
  const cache = useQueryClient()
  const [selected, setSelected] = useState<string>()
  const [showList, setShowList] = useState(false)
  const [search, setSearch] = useState('')
  const [input, setInput] = useState('')
  const [voice, setVoice] = useState(false)
  const [creating, setCreating] = useState(false)
  const [partial, setPartial] = useState('')
  const [sending, setSending] = useState<string>()
  const [error, setError] = useState<unknown>()
  const transcript = useRef<HTMLDivElement>(null)
  const editor = useRef<TextAreaRef>(null)

  const conversations = useQuery({
    queryKey: [user?.id, 'ai-conversations'],
    queryFn: () => api<ConversationOverview[]>(conversationsUrl),
  })
  const detail = useQuery({
    queryKey: [user?.id, 'ai-detail', selected],
    queryFn: () => api<Conversation>(conversationsUrl + '/' + selected),
    enabled: Boolean(selected),
  })
  const history = detail.data?.messages ?? []
  const pending = detail.data?.pending
  const locked = creating || Boolean(sending)
  const initials = user?.real_name.trim().slice(0, 1)
  const filtered = (conversations.data ?? []).filter(item =>
    item.title.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase()),
  )

  useEffect(() => {
    if (transcript.current?.offsetHeight) transcript.current.scrollTop = transcript.current.scrollHeight
  }, [selected, history.length, sending, pending, showList, voice, partial])

  function openConversation(id: string) {
    if (selected !== id) setVoice(false)
    setSelected(id)
    setShowList(false)
    setError(undefined)
  }

  function storeConversation(current: Conversation) {
    cache.setQueryData([user?.id, 'ai-detail', current.id], current)
    void conversations.refetch()
  }

  async function createConversation() {
    const current = await api<Conversation>(conversationsUrl, {method: 'POST', body: {title: '新对话'}})
    storeConversation(current)
    openConversation(current.id)
    return current
  }

  async function startConversation() {
    setCreating(true)
    try {
      await createConversation()
    } catch (cause) {
      void message.error(cause instanceof Error ? cause.message : '新建对话失败')
    } finally {
      setCreating(false)
    }
  }

  async function send(value = input) {
    const text = value.trim()
    if (!text || locked) return
    setSending(text)
    setPartial('')
    setError(undefined)
    try {
      const current = selected ? detail.data : await createConversation()
      if (!current) throw new Error('对话正在加载，请稍后发送')
      const updated = await api<Conversation>(conversationsUrl + '/' + current.id + '/messages', {
        method: 'POST', body: {text, expected_version: current.version}, timeout: 260000, onText: setPartial,
      })
      storeConversation(updated)
      setInput('')
      void cache.invalidateQueries({predicate: q => !String(q.queryKey[1]).startsWith('ai-')})
    } catch (cause) {
      setError(cause)
      if (selected) void detail.refetch()
    } finally {
      setSending(undefined)
    }
  }

  const prompts = [
    ...(can('crm:read') ? ['查询我的客户列表'] : []),
    ...(can('scores:read') && user?.student_ids[0] ? ['查询学生' + user.student_ids[0] + '的成绩'] : []),
    ...(can('todos:read') ? ['查询我的到期待办'] : []),
    ...(can('leaves:read') ? ['查询我的待审批请假'] : []),
    ...(can('reports:write') ? ['提交日报，内容是完成联调验证，没有风险，明天继续测试'] : []),
    ...(can('reports:summary:read') ? ['查看今天所管组织的日报'] : []),
    ...(can('directory:read') ? ['查询组织架构'] : []),
  ]

  return <div className={'assistant-layout' + (showList ? ' assistant-layout--conversations' : '')}>
    <aside className="assistant-conversations" aria-label="会话列表">
      <header className="assistant-conversation-header">
        <div className="assistant-conversation-heading">
          <Button type="text" className="assistant-back-to-chat" aria-label="返回聊天" icon={<LeftOutlined/>}
            onClick={() => setShowList(false)}/>
          <h2>会话</h2>
        </div>
        <Button type="text" icon={<PlusOutlined/>} disabled={locked} loading={creating}
          onClick={() => void startConversation()}>新建对话</Button>
      </header>
      <div className="assistant-search">
        <Input aria-label="搜索会话" prefix={<SearchOutlined/>} value={search} allowClear
          placeholder="搜索会话" onChange={event => setSearch(event.target.value)}/>
      </div>
      <div className="assistant-conversation-list">
        <ErrorNotice error={conversations.error}/>
        {conversations.isLoading && <div className="assistant-list-empty"><Spin size="small"/></div>}
        {!conversations.isLoading && !conversations.error && !filtered.length &&
          <div className="assistant-list-empty">{search.trim() ? '没有匹配的会话' : '暂无会话'}</div>}
        {filtered.map(item => {
          const updated = chatTime(item.update_time)
          return <button key={item.id} type="button" aria-current={selected === item.id ? 'true' : undefined}
            className="assistant-conversation" disabled={locked} onClick={() => openConversation(item.id)}>
            <Avatar shape="square" size={36} className="assistant-avatar" icon={<MessageOutlined/>}/>
            <span className="assistant-conversation-title" title={item.title}>{item.title || '新对话'}</span>
            {updated && <time dateTime={updated.toISOString()}>{timestamp(updated)}</time>}
          </button>
        })}
      </div>
    </aside>
    <section className="assistant-chat" aria-label="ENT 助手聊天">
      <header className="assistant-chat-header">
        <Button type="text" className="assistant-list-button" aria-label="会话" icon={<LeftOutlined/>} disabled={locked}
          onClick={() => setShowList(true)}>会话</Button>
        <h1>ENT 助手</h1>
      </header>

      <div className="assistant-transcript" role="log" aria-label="消息记录" ref={transcript}
        aria-busy={Boolean(sending) || detail.isLoading}>
        {detail.isLoading && <div className="assistant-list-empty"><Spin size="small"/></div>}
        {!detail.isLoading && !detail.error && !history.length && !sending && <div className="assistant-welcome">
          <Avatar shape="square" size={48} className="assistant-avatar" icon={<RobotOutlined/>}/>
          <h2>你好，{user?.real_name}</h2>
          <div className="assistant-prompts">
            {prompts.map(prompt => <Button key={prompt} onClick={() => {
              setInput(prompt)
              editor.current?.focus()
            }}>{prompt}</Button>)}
          </div>
        </div>}
        {history.map((item, index) => {
          const date = chatTime(item.create_time)
          const previous = chatTime(history[index - 1]?.create_time)
          const showTime = date && (!previous || date.getTime() - previous.getTime() >= 5 * 60_000)
          return <div key={item.id}>
            {showTime && <time className="assistant-time" dateTime={date.toISOString()}>{timestamp(date, true)}</time>}
            <MessageBubble mine={item.role === 'user'} content={item.content} initials={initials}
              failed={(item.metadata?.http_status ?? item.metadata?.error_status ?? 0) >= 400}/>
          </div>
        })}
        {sending && <>
          <MessageBubble mine content={sending} initials={initials}/>
          {partial ? <MessageBubble mine={false} content={partial}/> : <div className="assistant-message">
            <Avatar shape="square" size={34} className="assistant-avatar" icon={<RobotOutlined/>}/>
            <div className="assistant-chat-bubble assistant-typing" role="status">助手正在回复…</div>
          </div>}
        </>}
        <ErrorNotice error={error || detail.error}/>
        {pending?.state === 'confirm' && <Card className="assistant-confirmation" size="small"
          title={'请核对：' + (labels[pending.intent] || '业务操作')} extra={<Tag color="orange">待确认</Tag>}>
          <div className="assistant-confirmation-fields">
            {Object.entries(pending.params ?? {}).map(([key, value]) => <div key={key}>
              <span>{fieldNames[key] || key}</span><Value value={value}/>
            </div>)}
          </div>
          <Space wrap>
            <Button type="primary" icon={<CheckOutlined/>} loading={Boolean(sending)} disabled={creating}
              onClick={() => void send('确认')}>确认执行</Button>
            <Button icon={<CloseOutlined/>} disabled={locked} onClick={() => void send('取消')}>取消操作</Button>
          </Space>
        </Card>}
        {pending?.state === 'id' && <Alert type="info" showIcon
          title={pending.field === 'leave_id' ? '请选择请假单编号' : '请选择客户编号'}
          description="请发送候选列表中的编号，例如“选择20”。"/>}
      </div>

      <div className="assistant-composer">
        {voice && <div className="assistant-voice"><ReportVoiceInput key={selected || 'new'} assistant disabled={locked}
          onInsert={text => {
            const next = input.trim() ? input + '\n' + text : text
            if (next.length > messageLimit) return false
            setInput(next)
            setVoice(false)
            editor.current?.focus()
            return true
          }}/></div>}
        <Input.TextArea ref={editor} aria-label="发送给AI的消息" className="assistant-input" variant="borderless"
          value={input} maxLength={messageLimit} placeholder="输入消息…"
          autoSize={{minRows: 2, maxRows: 4}} disabled={locked} onChange={event => setInput(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault()
              void send()
            }
          }}/>
        <div className="assistant-tools">
          <Button type="text" icon={<AudioOutlined/>} aria-expanded={voice} disabled={locked}
            onClick={() => setVoice(!voice)}>{voice ? '收起录音' : '录音转写'}</Button>
          <span className="assistant-keyboard-hint">Enter 发送 · Shift + Enter 换行</span>
          <Button type="primary" className="assistant-send" aria-label="发送" autoInsertSpace={false} loading={Boolean(sending)}
            disabled={creating || !input.trim() || Boolean(selected && !detail.data)} onClick={() => void send()}>发送</Button>
        </div>
      </div>
    </section>
  </div>
}
