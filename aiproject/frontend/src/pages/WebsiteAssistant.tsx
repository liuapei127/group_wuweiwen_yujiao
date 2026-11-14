import {useState} from 'react'
import {Alert, Card, Input, Space, Typography} from 'antd'
import {useMutation} from '@tanstack/react-query'

export type AssistantTurn = {role: 'user' | 'assistant'; content: string}
type Ask = (query: string, history: AssistantTurn[]) => Promise<{answer: string}>

export function WebsiteAssistant({title, ask}: {title: string; ask: Ask}) {
  const [question, setQuestion] = useState('')
  const [history, setHistory] = useState<AssistantTurn[]>([])
  const result = useMutation({
    mutationFn: (query: string) => ask(query, history),
    onSuccess: (data, query) => {
      setHistory(prev => [
        ...prev.slice(-10),
        {role: 'user', content: query},
        {role: 'assistant', content: data.answer},
      ])
    },
  })
  return <Card title={title} style={{marginBottom: 16}}>
    <Space orientation="vertical" style={{width: '100%'}}>
      <Input.Search aria-label="输入咨询问题" value={question} maxLength={500}
        placeholder="输入问题，请勿填写密码或个人证件号码"
        onChange={event => setQuestion(event.target.value)} enterButton="发送" loading={result.isPending}
        onSearch={value => {
          const query = value.trim()
          if (query && !result.isPending) result.mutate(query)
        }}/>
      {result.error && <Alert type="error" showIcon title={result.error.message}/>}
      {result.data && <Typography.Paragraph style={{whiteSpace: 'pre-wrap'}}>{result.data.answer}</Typography.Paragraph>}
    </Space>
  </Card>
}
