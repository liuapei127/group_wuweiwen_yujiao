import {useEffect, useRef, useState} from 'react'
import {Alert, Button, Empty, Input, Space, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'

type Turn = {id?: number; role: 'user' | 'assistant'; content: string; create_time?: string}
type Conversation = {id: string; title: string; update_time?: string}
type Request = <T>(path: string, method?: string, body?: unknown) => Promise<T>

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
  const [question, setQuestion] = useState('')
  const [pendingText, setPendingText] = useState<string>()
  const bottom = useRef<HTMLDivElement>(null)

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
    mutationFn: () => request<Conversation>('/api/v1/student/assistant/conversations', 'POST', {}),
    onSuccess: row => {
      setActiveId(row.id)
      void cache.invalidateQueries({queryKey: ['visitor', 'student', 'assistant', 'conversations']})
    },
  })

  const send = useMutation({
    mutationFn: async (query: string) => {
      let conversationId = activeId
      if (!conversationId) {
        const created = await request<Conversation>('/api/v1/student/assistant/conversations', 'POST', {})
        conversationId = created.id
        setActiveId(created.id)
      }
      return request<{answer: string; conversation_id: string}>(
        '/api/v1/student/assistant',
        'POST',
        {query, conversation_id: conversationId},
      )
    },
    onMutate: query => setPendingText(query),
    onSuccess: async (data) => {
      setQuestion('')
      setPendingText(undefined)
      if (data.conversation_id) setActiveId(data.conversation_id)
      await cache.invalidateQueries({queryKey: ['visitor', 'student', 'assistant', 'conversations']})
      await cache.invalidateQueries({
        queryKey: ['visitor', 'student', 'assistant', 'conversation', data.conversation_id || activeId],
      })
      // 助手可能刚提交了请假或投诉，切到对应页签时要能看到最新单据
      await cache.invalidateQueries({queryKey: ['visitor', 'student', 'leaves']})
      await cache.invalidateQueries({queryKey: ['visitor', 'student', 'complaints']})
      await cache.invalidateQueries({queryKey: ['visitor', 'student', 'notifications']})
    },
    onError: () => setPendingText(undefined),
  })

  useEffect(() => {
    if (!activeId && conversations.data?.[0]?.id) setActiveId(conversations.data[0].id)
  }, [activeId, conversations.data])

  useEffect(() => {
    bottom.current?.scrollIntoView({behavior: 'smooth', block: 'end'})
  }, [detail.data?.messages, pendingText, send.isPending])

  const messages = detail.data?.messages || []

  function submit(raw: string) {
    const query = raw.trim()
    if (!query || send.isPending) return
    send.mutate(query)
  }

  return (
    <section className="assistant-shell" aria-label="学生助手">
      <aside className="assistant-shell__aside">
        <div className="assistant-shell__aside-head">
          <Typography.Text strong>对话记录</Typography.Text>
          <Button size="small" type="primary" loading={create.isPending}
            onClick={() => create.mutate()}>
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
              onClick={() => setActiveId(item.id)}
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

        <div className="assistant-panel__thread" role="log" aria-live="polite">
          {!activeId && !send.isPending && (
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
          {send.isPending && (
            <div className="assistant-bubble assistant-bubble--bot assistant-bubble--pending">
              正在理解并办理…
            </div>
          )}
          <div ref={bottom}/>
        </div>

        <div className="assistant-panel__hints">
          {HINTS.map(item => (
            <button key={item} type="button" className="assistant-hint" disabled={send.isPending}
              onClick={() => submit(item)}>
              {item}
            </button>
          ))}
        </div>

        {send.error && <Alert type="error" showIcon title={(send.error as Error).message} style={{marginBottom: 12}}/>}
        {create.error && <Alert type="error" showIcon title={(create.error as Error).message} style={{marginBottom: 12}}/>}
        {conversations.error && <Alert type="error" showIcon title={(conversations.error as Error).message} style={{marginBottom: 12}}/>}

        <Space.Compact style={{width: '100%'}}>
          <Input.TextArea
            aria-label="输入要办的事"
            value={question}
            maxLength={1000}
            autoSize={{minRows: 2, maxRows: 5}}
            placeholder="例如：病假，2026-11-17 到 2026-11-19，身体不适要看病"
            onChange={event => setQuestion(event.target.value)}
            onPressEnter={event => {
              // 中文输入法选词时的回车不能直接发送
              if (event.nativeEvent.isComposing || event.keyCode === 229) return
              if (!event.shiftKey) {
                event.preventDefault()
                submit(question)
              }
            }}
          />
          <Button type="primary" loading={send.isPending} onClick={() => submit(question)}>发送</Button>
        </Space.Compact>
      </div>
    </section>
  )
}
