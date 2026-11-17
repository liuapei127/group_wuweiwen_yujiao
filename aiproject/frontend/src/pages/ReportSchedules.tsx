import {Button, Card, Form, Input, Select, Space, Tag, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ErrorNotice} from '../components/shared'
import {api} from '../lib/api'
import {ReportHistory} from './ReportHistory'

type Schedule = {
  kind: string; title: string; weekly: boolean; run_at: string; enabled: boolean; include_ai:boolean; last_run_time: string | null
}
const endpoint = '/api/v1/reporting'

export function ReportSchedules() {
  const {user} = useAuth()
  const cache = useQueryClient()
  const plans = useQuery({
    queryKey: [user?.id, 'report-schedules'],
    queryFn: () => api<{items: Schedule[]}>(endpoint + '/schedules'),
  })
  const save = useMutation({
    mutationFn: (values: {kind: string; run_at: string; enabled: boolean; weekly?: boolean;include_ai?:boolean}) =>
      api<{items: Schedule[]}>(endpoint + '/schedules', {method: 'PUT', body: values}),
    onSuccess: result => cache.setQueryData([user?.id, 'report-schedules'], result),
  })
  return <Space orientation="vertical" size="middle" style={{width: '100%'}}>
    <Card title="报表计划（北京时间）" loading={plans.isPending}>
      <ErrorNotice error={plans.error}/><ErrorNotice error={save.error}/>
      {(plans.data?.items || []).map(plan => <Form key={plan.kind + ':' + plan.run_at + ':' + plan.enabled + ':' + plan.weekly + ':' + plan.include_ai}
        layout="inline" style={{marginBottom: 12}} initialValues={{run_at: plan.run_at, enabled: plan.enabled, weekly:plan.weekly,include_ai:plan.include_ai}}
        onFinish={values => save.mutate({kind: plan.kind, ...values})}>
        <Form.Item><Typography.Text strong>{plan.kind==='customer_ops'?'客户经营报告':plan.title}</Typography.Text> {plan.kind!=='customer_ops' && <Tag>{plan.weekly ? '每周一' : '每天'}</Tag>}</Form.Item>
        {plan.kind==='customer_ops' && <Form.Item name="weekly" label="频率"><Select options={[{value:false,label:'每天'},{value:true,label:'每周一'}]}/></Form.Item>}
        <Form.Item name="run_at" label="生成时间" rules={[{required: true}]}><Input type="time" step={60}/></Form.Item>
        <Form.Item name="enabled" label="状态"><Select options={[{value: true, label: '启用'}, {value: false, label: '停用'}]}/></Form.Item>
        <Form.Item name="include_ai" label="AI 摘要"><Select options={[{value:true,label:'生成'},{value:false,label:'关闭'}]}/></Form.Item>
        <Form.Item><Button htmlType="submit" loading={save.isPending && save.variables?.kind === plan.kind}>保存</Button></Form.Item>
        {plan.last_run_time && <Form.Item><Typography.Text type="secondary">最近生成 {plan.last_run_time.replace('T', ' ')}</Typography.Text></Form.Item>}
      </Form>)}
    </Card>
    <ReportHistory/>
  </Space>
}
