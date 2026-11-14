import {useEffect, useRef, useState} from 'react'
import {Alert, Button, Input, Space, Typography} from 'antd'
import {useMutation} from '@tanstack/react-query'

export type AssistantTurn = {role: 'user' | 'assistant'; content: string}
type Ask = (query: string, history: AssistantTurn[]) => Promise<{answer: string}>

export function WebsiteAssistant({
  title,
  ask,
  hints = [],
  intro = '直接说你想了解的事。涉及请假、投诉、学籍进度请先登录学生账号。',
}: {
  title: string
  ask: Ask
  hints?: string[]
  intro?: string
}) {
  const [question, setQuestion] = useState('')
  const [history, setHistory] = useState<AssistantTurn[]>([])
  const bottom = useRef<HTMLDivElement>(null)
  const result = useMutation({
    mutationFn: (query: string) => ask(query, history),
    onSuccess: (data, query) => {
      setHistory(prev => [
        ...prev.slice(-20),
        {role: 'user', content: query},
        {role: 'assistant', content: data.answer},
      ])
      setQuestion('')
    },
  })

  useEffect(() => {
    bottom.current?.scrollIntoView({behavior: 'smooth', block: 'end'})
  }, [history, result.isPending])

  function send(raw: string) {
    const query = raw.trim()
    if (!query || result.isPending) return
    result.mutate(query)
  }

  return (
    <section className="assistant-panel" aria-label={title}>
      <header className="assistant-panel__head">
        <div>
          <Typography.Title level={4} style={{margin: 0}}>{title}</Typography.Title>
          <Typography.Paragraph type="secondary" style={{margin: '6px 0 0'}}>
            {intro}
          </Typography.Paragraph>
        </div>
        {history.length > 0 && (
          <Button type="text" onClick={() => { setHistory([]); result.reset() }}>清空对话</Button>
        )}
      </header>

      <div className="assistant-panel__thread" role="log" aria-live="polite">
        {history.length === 0 && !result.isPending && (
          <div className="assistant-bubble assistant-bubble--bot assistant-bubble--intro">
            {intro}
          </div>
        )}
        {history.map((turn, index) => (
          <div
            key={`${turn.role}-${index}-${turn.content.slice(0, 12)}`}
            className={`assistant-bubble assistant-bubble--${turn.role === 'user' ? 'me' : 'bot'}`}
          >
            <span className="assistant-bubble__role">{turn.role === 'user' ? '我' : '助手'}</span>
            <div className="assistant-bubble__text">{turn.content}</div>
          </div>
        ))}
        {result.isPending && (
          <div className="assistant-bubble assistant-bubble--bot assistant-bubble--pending">
            正在理解你的意思…
          </div>
        )}
        <div ref={bottom}/>
      </div>

      {hints.length > 0 && (
        <div className="assistant-panel__hints">
          {hints.map(item => (
            <button key={item} type="button" className="assistant-hint" disabled={result.isPending}
              onClick={() => send(item)}>
              {item}
            </button>
          ))}
        </div>
      )}

      {result.error && <Alert type="error" showIcon title={result.error.message} style={{marginBottom: 12}}/>}

      <Space.Compact style={{width: '100%'}}>
        <Input.TextArea
          aria-label="输入要办的事"
          value={question}
          maxLength={1000}
          autoSize={{minRows: 2, maxRows: 5}}
          placeholder="例如：病假，2026-11-17 到 2026-11-19，身体不适要看病"
          onChange={event => setQuestion(event.target.value)}
          onPressEnter={event => {
            if (!event.shiftKey) {
              event.preventDefault()
              send(question)
            }
          }}
        />
        <Button type="primary" loading={result.isPending} onClick={() => send(question)}>
          发送
        </Button>
      </Space.Compact>
    </section>
  )
}
