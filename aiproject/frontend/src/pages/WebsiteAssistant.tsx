import {useEffect, useRef, useState} from 'react'
import {useMutation} from '@tanstack/react-query'
import {Drawer} from 'antd'
import {ArrowUpOutlined, CloseOutlined, CustomerServiceOutlined, ReloadOutlined, RobotOutlined} from '@ant-design/icons'

export type AssistantTurn = {role: 'user' | 'assistant'; content: string}
type Ask = (query: string, history: AssistantTurn[], sessionId?: string) => Promise<{answer: string; session_id?: string}>

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
  const [history, setHistory] = useState<AssistantTurn[]>([])
  const session = useRef<string | undefined>(undefined)
  const generation = useRef(0)
  const thread = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLInputElement>(null)
  const isOpen = open ?? innerOpen

  function setOpen(value: boolean) {
    onOpenChange?.(value)
    if (open === undefined) setInnerOpen(value)
  }

  const result = useMutation({
    mutationFn: ({query}: {query: string; generation: number}) => ask(query, history, session.current),
    onSuccess: (data, {query, generation: sentAt}) => {
      if (generation.current !== sentAt) return
      if (data.session_id) session.current = data.session_id
      setHistory(prev => [
        ...prev.slice(-20),
        {role: 'user', content: query},
        {role: 'assistant', content: data.answer},
      ])
      setQuestion('')
    },
  })

  useEffect(() => {
    const messages = thread.current
    if (isOpen && messages) messages.scrollTop = messages.scrollHeight
  }, [isOpen, history, result.isPending])

  function send(raw: string) {
    const query = raw.trim()
    if (!query || result.isPending) return
    result.mutate({query, generation: generation.current})
  }

  function reset() {
    generation.current += 1
    session.current = undefined
    setHistory([])
    setQuestion('')
    result.reset()
  }

  return <>
    <button type="button" className="assistant-launcher"
      aria-label={'打开' + title} title={'打开' + title} aria-haspopup="dialog" aria-expanded={isOpen}
      tabIndex={isOpen ? -1 : undefined} onClick={() => setOpen(true)}>
      <CustomerServiceOutlined />
      <span className="assistant-launcher__pulse" />
    </button>

    <Drawer
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
        header: {background: 'var(--brand-900)', borderBottom: 0},
        body: {display: 'flex', flexDirection: 'column', overflow: 'hidden', padding: 0},
        mask: {background: 'rgba(6, 31, 28, .42)'},
      }}
      title={<div className="assistant-widget__head">
        <span className="assistant-widget__mark"><RobotOutlined /></span>
        <div>
          <div className="assistant-widget__title">{title}</div>
          <div className="assistant-widget__sub">智能客服 · 在线</div>
        </div>
      </div>}
      extra={<div className="assistant-widget__tools">
        <button type="button" aria-label="清空对话" title="清空对话" onClick={reset}><ReloadOutlined /></button>
        <button type="button" aria-label="关闭客服" title="关闭" onClick={() => setOpen(false)}><CloseOutlined /></button>
      </div>}
    >
      <div ref={thread} className="assistant-widget__thread" role="log" aria-live="polite">
        <div className="assistant-msg assistant-msg--bot">{intro}</div>
        {history.map((turn, index) => <div
          key={`${turn.role}-${index}-${turn.content.slice(0, 12)}`}
          className={'assistant-msg assistant-msg--' + (turn.role === 'user' ? 'me' : 'bot')}>
          <span className="assistant-msg__role">{turn.role === 'user' ? '我' : '助手'}</span>
          <div className="assistant-msg__text">{turn.content}</div>
        </div>)}
        {result.isPending && <div className="assistant-msg assistant-msg--bot assistant-msg--pending">
          正在为你查询 <i /><i /><i />
        </div>}
        {result.error && <div className="assistant-msg assistant-msg--error">{result.error.message}</div>}
      </div>

      {hints.length > 0 && <div className="assistant-widget__hints">
        {hints.map(item => <button key={item} type="button" disabled={result.isPending}
          onClick={() => send(item)}>{item}</button>)}
      </div>}

      <div className="assistant-widget__composer">
        <input ref={input} aria-label="输入想了解的问题" value={question} maxLength={1000}
          placeholder="输入你想了解的问题…" onChange={event => setQuestion(event.target.value)}
          onKeyDown={event => {
            if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
              event.preventDefault()
              send(question)
            }
          }} />
        <button type="button" className="assistant-widget__send" aria-label="发送"
          disabled={!question.trim() || result.isPending} onClick={() => send(question)}>
          <ArrowUpOutlined />
        </button>
      </div>
    </Drawer>
  </>
}
