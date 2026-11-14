import {useState} from 'react'
import {useQuery} from '@tanstack/react-query'
import {Alert, Card, Segmented, Space, Typography} from 'antd'

type Country = 'Singapore' | 'Germany'
type PolicyResource = {title: string; description: string; publisher: string; url: string}
export type PolicyData = {country: Country | null; resources: PolicyResource[]}

export function PolicyCards({resources}: {resources: PolicyResource[]}) {
  return <div className="visitor-programs">
    {resources.map(resource => <Card key={resource.url} title={resource.title}>
      <Typography.Paragraph>{resource.description}</Typography.Paragraph>
      <Typography.Paragraph type="secondary">{resource.publisher}</Typography.Paragraph>
      <Typography.Link href={resource.url} target="_blank" rel="noopener noreferrer">查看官方说明</Typography.Link>
    </Card>)}
  </div>
}

export function WebsitePolicies({request}: {request: <T>(path: string) => Promise<T>}) {
  const [country, choose] = useState<Country>('Singapore')
  const result = useQuery({
    queryKey: ['visitor', 'policies', country],
    queryFn: () => request<PolicyData>('/api/v1/visitors/policies?country=' + country),
  })
  return <Space orientation="vertical" size="middle" style={{width: '100%'}}>
    <Segmented<Country> value={country} onChange={choose} options={[
      {label: '新加坡', value: 'Singapore'}, {label: '德国', value: 'Germany'},
    ]}/>
    {result.error && <Alert type="error" showIcon title={result.error.message}/>}
    {result.isPending && <Typography.Text>正在读取留学政策…</Typography.Text>}
    {result.data && <PolicyCards resources={result.data.resources}/>}
  </Space>
}
