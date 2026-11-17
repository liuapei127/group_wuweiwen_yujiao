import {useEffect, useRef, useState} from 'react'
import {Alert, Button, Empty, Input, Space, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'

type Turn = {id?: number; role: 'user' | 'assistant'; content: string; create_time?: string}
type Conversation = {id: string; title: string; update_time?: string}
type Request = <T>(path: string, method?: string, body?: unknown, onText?: (text: string) => void) => Promise<T>

type SendTurn = {query: string; conversationId?: string; selection: number}

const HINTS = [
  '我要请假',
  '病假，2026-11-17 到 2026-11-19，身体不适',
  '查进度',
  '我要投诉',
  '最近考试截止是什么时候',
]

export function StudentAssistant({request}: {request: Request}) {
  const cache = useQueryClient()
  const [activeId, setActiveId] = useState<string>()
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [partial, setPartial] = useState('')
  const [showNew, setShowNew] = useState(false)
  const thread = useRef<HTMLDivElement>(null)
  const stickToEnd = useRef(true)
  const selectionVersion = useRef(0)

  const conversations = useQuery({
    queryKey: ['visitor', 'student', 'assistant', 'conversations'],
    queryFn: () => request<Conversation[]>('/api/v1/student/assistant/conversations'),
  })

  const detail = useQuery({
    queryKey: ['visitor', 'student', 'assistant', 'conversation', activeId],
    enabled: !!activeId,
    queryFn: () => request<{id: string; title: string; messages: Turn[]}>(
      '/api/v1/student/assistant/conversations/' + activeId,
    ),
  })

  const create = useMutation({
    mutationFn: (_selection: number) => request<Conversation>('/api/v1/student/assistant/conversations', 'POST', {}),
    onSuccess: (row, selection) => {
      if (selectionVersion.current === selection) choose(row.id)
      void cache.invalidateQueries({queryKey: ['visitor', 'student', 'assistant', 'conversations']})
    },
  })

  const send = useMutation({
    mutationFn: ({query, conversationId}: SendTurn) => request<{answer: string; conversation_id: string}>(
      '/api/v1/student/assistant', 'POST', {query, conversation_id: conversationId}, setPartial,
    ),
    onSuccess: async (data, turn) => {
      const key = turn.conversationId || ''
      setDrafts(current => (current[key] || '').trim() === turn.query ? {...current, [key]: ''} : current)
      if (!turn.conversationId && data.conversation_id && selectionVersion.current === turn.selection) {
        setDrafts(current => current[''] ? {...current, [data.conversation_id]: current[''], '': ''} : current)
        choose(data.conversation_id)
      }
      await Promise.all([
        cache.invalidateQueries({queryKey: ['visitor', 'student', 'assistant', 'conversations']}),
        cache.invalidateQueries({
          queryKey: ['visitor', 'student', 'assistant', 'conversation', data.conversation_id || turn.conversationId],
        }),
        ...['leaves', 'complaints', 'notifications'].map(key => cache.invalidateQueries({queryKey: ['visitor', 'student', key]})),
      ])
    },
  })

  useEffect(() => {
    if (!activeId && !send.isPending && !create.isPending && conversations.data?.[0]?.id) {
      setActiveId(conversations.data[0].id)
    }
  }, [activeId, conversations.data, create.isPending, send.isPending])

  const ownRequest = send.variables?.conversationId === activeId
  const pendingText = ownRequest && send.isPending ? send.variables?.query : undefined
  const messages = detail.data?.messages || []
  const question = drafts[activeId || ''] || ''

  useEffect(() => {
    const node = thread.current
    if (!node) return
    if (stickToEnd.current) node.scrollTop = node.scrollHeight
    else if (detail.data?.messages.length) setShowNew(true)
  }, [activeId, detail.data?.messages, pendingText, partial])

  function choose(id: string) {
    selectionVersion.current += 1
    stickToEnd.current = true
    setShowNew(false)
    setActiveId(id)
  }

  function submit(raw: string) {
    const query = raw.trim()
    if (!query || send.isPending || create.isPending) return
    stickToEnd.current = true
    setShowNew(false)
    setPartial('')
    send.mutate({query, conversationId: activeId, selection: selectionVersion.current})
  }

  return (
    <section className="assistant-shell" aria-label="学生助手">
      <aside className="assistant-shell__aside">
        <div className="assistant-shell__aside-head">
          <Typography.Text strong>对话记录</Typography.Text>
          <Button size="small" type="primary" loading={create.isPending}
            onClick={() => create.mutate(++selectionVersion.current)}>
            新对话
          </Button>
        </div>
        <div className="assistant-shell__list">
          {(conversations.data || []).length === 0 && !conversations.isFetching && (
            <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="还没有对话"/>
          )}
          {(conversations.data || []).map(item => (
            <button
              key={item.id}
              type="button"
              className={'assistant-shell__item' + (item.id === activeId ? ' is-active' : '')}
              aria-pressed={item.id === activeId}
              onClick={() => choose(item.id)}
            >
              <span>{item.title || '新对话'}</span>
            </button>
          ))}
        </div>
      </aside>

      <div className="assistant-shell__main">
        <header className="assistant-panel__head">
          <div>
            <Typography.Title level={4} style={{margin: 0}}>学生助手</Typography.Title>
            <Typography.Paragraph type="secondary" style={{margin: '6px 0 0'}}>
              每个账号有独立记忆，不用每次把全部聊天记录塞回来。信息够了会直接帮你办。
            </Typography.Paragraph>
          </div>
        </header>

        <div ref={thread} className="assistant-panel__thread" role="log" aria-live="polite" onScroll={event => {
          const node = event.currentTarget
          stickToEnd.current = node.scrollHeight - node.scrollTop - node.clientHeight <= 60
          if (stickToEnd.current) setShowNew(false)
        }}>
          {!activeId && !pendingText && (
            <div className="assistant-bubble assistant-bubble--bot assistant-bubble--intro">
              直接说想办的事。例如「病假，2026-11-17 到 19 号，身体不适」。点「新对话」可开一条干净会话。
            </div>
          )}
          {messages.map(turn => (
            <div
              key={turn.id || `${turn.role}-${turn.content.slice(0, 16)}`}
              className={`assistant-bubble assistant-bubble--${turn.role === 'user' ? 'me' : 'bot'}`}
            >
              <span className="assistant-bubble__role">{turn.role === 'user' ? '我' : '助手'}</span>
              <div className="assistant-bubble__text">{turn.content}</div>
            </div>
          ))}
          {pendingText && (
            <div className="assistant-bubble assistant-bubble--me">
              <span className="assistant-bubble__role">我</span>
              <div className="assistant-bubble__text">{pendingText}</div>
            </div>
          )}
          {pendingText && (
            <div className={'assistant-bubble assistant-bubble--bot' + (partial ? '' : ' assistant-bubble--pending')}>
              {partial || '正在理解并办理…'}
            </div>
          )}
        </div>
        {showNew && <Button type="link" size="small" onClick={() => {
          if (thread.current) thread.current.scrollTop = thread.current.scrollHeight
          stickToEnd.current = true
          setShowNew(false)
        }}>查看新消息</Button>}

        <div className="assistant-panel__hints">
          {HINTS.map(item => (
            <button key={item} type="button" className="assistant-hint" disabled={send.isPending}
              onClick={() => submit(item)}>
              {item}
            </button>
          ))}
        </div>

        {ownRequest && send.error && <Alert type="error" showIcon title={(send.error as Error).message} style={{marginBottom: 12}}/>}
        {create.error && <Alert type="error" showIcon title={(create.error as Error).message} style={{marginBottom: 12}}/>}
        {conversations.error && <Alert type="error" showIcon title={(conversations.error as Error).message} style={{marginBottom: 12}}/>}

        <Space.Compact style={{width: '100%'}}>
          <Input.TextArea
            aria-label="输入要办的事"
            value={question}
            maxLength={1000}
            autoSize={{minRows: 2, maxRows: 5}}
            placeholder="例如：病假，2026-11-17 到 2026-11-19，身体不适要看病"
            onChange={event => setDrafts(current => ({...current, [activeId || '']: event.target.value}))}
            onPressEnter={event => {
              // 中文输入法选词时的回车不能直接发送
              if (event.nativeEvent.isComposing || event.keyCode === 229) return
              if (!event.shiftKey) {
                event.preventDefault()
                submit(question)
              }
            }}
          />
          <Button type="primary" loading={!!pendingText} disabled={send.isPending || create.isPending} onClick={() => submit(question)}>发送</Button>
        </Space.Compact>
      </div>
    </section>
  )
}
