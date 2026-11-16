import {useState} from 'react'
import {Button, Card, Input, Space, Typography} from 'antd'

export type GuideTopic = {key: string; label: string; keywords: string[]; answer: string}

export function WebsiteGuide({topics, open, showSearch = true}: {
  topics: GuideTopic[]
  open?: (key: string) => void
  showSearch?: boolean
}) {
  const [matches, setMatches] = useState<GuideTopic[]>()
  return <Card title="服务指引">
    <Space orientation="vertical" size="middle" style={{width: '100%'}}>
      {showSearch && <Input.Search aria-label="输入想办理的事项" placeholder="输入想了解或办理的事项" maxLength={120} allowClear
        enterButton="查询" onSearch={question => {
          const text = question.trim().toLowerCase()
          setMatches(text ? topics.filter(topic => topic.keywords.some(word => text.includes(word))) : undefined)
        }}/>}
      <Space wrap>{topics.map(topic =>
        <Button key={topic.key} onClick={() => setMatches([topic])}>{topic.label}</Button>
      )}</Space>
      {matches?.length === 0 && <Typography.Text>请选择上方的服务类别。</Typography.Text>}
      {matches?.map(topic => <div key={topic.key}>
        <Typography.Text strong>{topic.label}</Typography.Text>
        <Typography.Paragraph>{topic.answer}</Typography.Paragraph>
        {open && <Button type="link" onClick={() => open(topic.key)}>前往{topic.label}</Button>}
      </div>)}
    </Space>
  </Card>
}
