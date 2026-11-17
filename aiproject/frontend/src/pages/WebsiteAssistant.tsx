import {Fragment, useEffect, useRef, useState} from 'react'
import {useMutation} from '@tanstack/react-query'
import {Drawer, Input} from 'antd'
import type {TextAreaRef} from 'antd/es/input/TextArea'
import {CloseOutlined, CustomerServiceOutlined, MessageOutlined, ReloadOutlined, RobotOutlined, SendOutlined, SmileOutlined, UserOutlined} from '@ant-design/icons'

export type AssistantTurn = {role: 'user' | 'assistant'; content: string; at?: string}
type Ask = (query: string, history: AssistantTurn[], sessionId: string | undefined, onText: (text: string) => void) => Promise<{answer: string; session_id?: string}>

function clock() {
  return new Date().toLocaleTimeString('zh-CN', {hour: '2-digit', minute: '2-digit', hour12: false})
}

/** 单条 IM 消息：头像 + 带小尖角的气泡 + 时间。用户消息靠右、客服消息靠左。 */
function ChatRow({side, text, typing}: {side: 'bot' | 'me'; text?: string; typing?: boolean}) {
  return <div className={'wa-row wa-row--' + side}>
    <span className={'wa-avatar wa-avatar--' + side} aria-hidden="true">
      {side === 'bot' ? <RobotOutlined /> : <UserOutlined />}
    </span>
    <div className="wa-bubble-wrap">
      <div className="wa-bubble">
        {typing
          ? <span className="wa-typing" aria-label="对方正在输入"><i /><i /><i /></span>
          : text}
      </div>
    </div>
  </div>
}

/**
 * 官网客服可通过右下角按钮或首屏入口打开右侧抽屉。
 * open / onOpenChange 可选；传入即为受控模式（由首屏按钮打开），
 * 不传则组件自己管理开关（登录后页面使用）。
 */
export function WebsiteAssistant({
  title,
  ask,
  hints = [],
  intro = '你好，我是粤教升学助手。关于留学项目、活动预约和材料提交，都可以问我。',
  open,
  onOpenChange,
}: {
  title: string
  ask: Ask
  hints?: string[]
  intro?: string
  open?: boolean
  onOpenChange?: (open: boolean) => void
}) {
  const [innerOpen, setInnerOpen] = useState(false)
  const [question, setQuestion] = useState('')
  const [partial, setPartial] = useState('')
  const [history, setHistory] = useState<AssistantTurn[]>([])
  const [sessionStart, setSessionStart] = useState(clock)
  const [hintsOn, setHintsOn] = useState(true)
  const session = useRef<string | undefined>(undefined)
  const generation = useRef(0)
  const thread = useRef<HTMLDivElement>(null)
  const input = useRef<TextAreaRef>(null)
  const isOpen = open ?? innerOpen

  function setOpen(value: boolean) {
    onOpenChange?.(value)
    if (open === undefined) setInnerOpen(value)
  }

  const result = useMutation({
    mutationFn: ({query, generation: sentAt}: {query: string; generation: number}) =>
      ask(query, history, session.current, text => {
        if (generation.current === sentAt) setPartial(text)
      }),
    onSuccess: (data, {query, generation: sentAt}) => {
      if (generation.current !== sentAt) return
      if (data.session_id) session.current = data.session_id
      const at = clock()
      setHistory(prev => [
        ...prev.slice(-20),
        {role: 'user', content: query, at},
        {role: 'assistant', content: data.answer, at},
      ])
      setQuestion('')
    },
  })

  useEffect(() => {
    const messages = thread.current
    if (isOpen && messages) messages.scrollTop = messages.scrollHeight
  }, [isOpen, history, result.isPending, partial])

  function send(raw: string) {
    const query = raw.trim()
    if (!query || result.isPending) return
    setPartial('')
    result.mutate({query, generation: generation.current})
  }

  function reset() {
    generation.current += 1
    session.current = undefined
    setPartial('')
    setHistory([])
    setQuestion('')
    setSessionStart(clock())
    setHintsOn(true)
    result.reset()
  }

  function insertEmoji() {
    setQuestion(prev => (prev + '😊').slice(0, 1000))
    input.current?.focus({preventScroll: true})
  }

  return <>
    <button type="button" className="assistant-launcher"
      aria-label={'打开' + title} title={'打开' + title} aria-haspopup="dialog" aria-expanded={isOpen}
      tabIndex={isOpen ? -1 : undefined} onClick={() => setOpen(true)}>
      <CustomerServiceOutlined />
      <span className="assistant-launcher__pulse" />
    </button>

    <Drawer
      className="wa-drawer"
      placement="right"
      size="min(100%, 420px)"
      open={isOpen}
      onClose={() => setOpen(false)}
      afterOpenChange={opened => {
        if (opened && window.matchMedia('(pointer: fine)').matches) {
          input.current?.focus({preventScroll: true})
        }
      }}
      closable={false}
      mask={{closable: true}}
      styles={{
        header: {background: 'var(--brand-900)', borderBottom: 0, padding: '13px 16px'},
        body: {display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 0},
        mask: {background: 'rgba(6, 31, 28, .42)'},
      }}
      title={<div className="wa-head">
        <span className="wa-head__avatar"><RobotOutlined /><i className="wa-head__online" /></span>
        <div className="wa-head__meta">
          <div className="wa-head__title">{title}</div>
          <div className="wa-head__status">在线 · 通常几秒内回复</div>
        </div>
      </div>}
      extra={<div className="wa-tools">
        <button type="button" aria-label="清空对话" title="清空对话" onClick={reset}><ReloadOutlined /></button>
        <button type="button" aria-label="关闭客服" title="关闭" onClick={() => setOpen(false)}><CloseOutlined /></button>
      </div>}
    >
      <div ref={thread} className="wa-thread" role="log" aria-live="polite" aria-label="客服对话记录">
        <div className="wa-time"><span>今天 {sessionStart}</span></div>
        <ChatRow side="bot" text={intro} />
        {history.map((turn, index) => <Fragment key={`${turn.role}-${index}-${turn.content.slice(0, 12)}`}>
          {turn.role === 'user' && turn.at && <div className="wa-time"><span>{turn.at}</span></div>}
          <ChatRow side={turn.role === 'user' ? 'me' : 'bot'} text={turn.content} />
        </Fragment>)}
        {result.isPending && <>
          <ChatRow side="me" text={result.variables.query}/>
          <ChatRow side="bot" typing={!partial} text={partial}/>
        </>}
        {result.error && <div className="wa-system" role="alert">{result.error.message}</div>}
      </div>

      {hints.length > 0 && hintsOn && <div className="wa-hints">
        <div className="wa-hints__label"><MessageOutlined /> 猜你想问</div>
        <div className="wa-hints__list">
          {hints.map(item => <button key={item} type="button" disabled={result.isPending}
            onClick={() => send(item)}>{item}</button>)}
        </div>
      </div>}

      <div className="wa-composer">
        <div className="wa-composer__tools">
          <button type="button" aria-label="插入表情" title="插入表情" onClick={insertEmoji}><SmileOutlined /></button>
          {hints.length > 0 && <button type="button" className={hintsOn ? 'is-on' : ''}
            aria-label="切换猜你想问" aria-pressed={hintsOn} title="猜你想问"
            onClick={() => setHintsOn(value => !value)}><MessageOutlined /></button>}
          <span className="wa-composer__tip">Enter 发送 · Shift+Enter 换行</span>
        </div>
        <div className="wa-composer__row">
          <Input.TextArea ref={input} aria-label="输入想了解的问题" value={question} maxLength={1000}
            autoSize={{minRows: 1, maxRows: 5}}
            placeholder="输入你想了解的问题…" onChange={event => setQuestion(event.target.value)}
            onKeyDown={event => {
              if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing && event.keyCode !== 229) {
                event.preventDefault()
                send(question)
              }
            }} />
          <button type="button" className="wa-send" aria-label="发送"
            disabled={!question.trim() || result.isPending} onClick={() => send(question)}>
            <SendOutlined />
          </button>
        </div>
      </div>
    </Drawer>
  </>
}
