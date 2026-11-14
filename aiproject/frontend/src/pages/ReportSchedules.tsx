import {useState} from 'react'
import {Button, Card, Form, Input, Select, Space, Table, Tag, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {DetailDrawer, ErrorNotice} from '../components/shared'
import {api, query} from '../lib/api'

type Schedule = {
  kind: string; title: string; weekly: boolean; run_at: string; enabled: boolean; last_run_time: string | null
}
type ArchiveEntry = {
  id: number; report_title?: string; period_start?: string; period_end?: string
  report_content?: Record<string, unknown>; unavailable?: boolean
}
const endpoint = '/api/v1/reporting'
const pagination = 20
const statusLabels: Record<string, string> = {new: '新线索', contacting: '联系中', qualified: '已确认意向',
  signed: '已签约', lost: '已流失', pending: '待处理', processing: '处理中', resolved: '已处理',
  closed: '已关闭', following: '跟进中', dismissed: '已排除'}
const riskLabels: Record<string, string> = {low: '低', medium: '中', high: '高'}

function summarize(report: ArchiveEntry) {
  const content = report.report_content || {}
  const counts = (values: Record<string, unknown>) => Object.entries(values).map(([state, count]) => ({
    状态: statusLabels[state] || state, 数量: count,
  }))
  if (content.days) return {
    累计提交人次: content.submitted_employee_days,
    每日人数: (content.days as {report_date: string; submitted_employees: number}[]).map(row =>
      ({日期: row.report_date, 提交人数: row.submitted_employees})),
  }
  if (content.items) return {心理预警: (content.items as {status: string; risk_level: string; count: number}[]).map(row =>
    ({状态: statusLabels[row.status], 风险: riskLabels[row.risk_level], 数量: row.count}))}
  if (content.complaints_by_status) return {投诉状态: counts(content.complaints_by_status as Record<string, unknown>)}
  return {线索状态: counts((content.leads_by_status || {}) as Record<string, unknown>)}
}

export function ReportSchedules() {
  const {user} = useAuth()
  const cache = useQueryClient()
  const [before, setBefore] = useState<number>()
  const [detail, setDetail] = useState<ArchiveEntry>()
  const plans = useQuery({
    queryKey: [user?.id, 'report-schedules'],
    queryFn: () => api<{items: Schedule[]}>(endpoint + '/schedules'),
  })
  const records = useQuery({
    queryKey: [user?.id, 'report-archive', before],
    queryFn: () => api<ArchiveEntry[]>(endpoint + '/archive' + query({before_id: before})),
  })
  const save = useMutation({
    mutationFn: (values: {kind: string; run_at: string; enabled: boolean}) =>
      api<{items: Schedule[]}>(endpoint + '/schedules', {method: 'PUT', body: values}),
    onSuccess: result => cache.setQueryData([user?.id, 'report-schedules'], result),
  })
  return <Space orientation="vertical" size="middle" style={{width: '100%'}}>
    <Card title="报表计划（北京时间）" loading={plans.isPending}>
      <ErrorNotice error={plans.error}/><ErrorNotice error={save.error}/>
      {(plans.data?.items || []).map(plan => <Form key={plan.kind + ':' + plan.run_at + ':' + plan.enabled}
        layout="inline" style={{marginBottom: 12}} initialValues={{run_at: plan.run_at, enabled: plan.enabled}}
        onFinish={values => save.mutate({kind: plan.kind, ...values})}>
        <Form.Item><Typography.Text strong>{plan.title}</Typography.Text> <Tag>{plan.weekly ? '每周一' : '每天'}</Tag></Form.Item>
        <Form.Item name="run_at" label="生成时间" rules={[{required: true}]}><Input type="time" step={60}/></Form.Item>
        <Form.Item name="enabled" label="状态"><Select options={[{value: true, label: '启用'}, {value: false, label: '停用'}]}/></Form.Item>
        <Form.Item><Button htmlType="submit" loading={save.isPending && save.variables?.kind === plan.kind}>保存</Button></Form.Item>
        {plan.last_run_time && <Form.Item><Typography.Text type="secondary">最近生成 {plan.last_run_time.replace('T', ' ')}</Typography.Text></Form.Item>}
      </Form>)}
    </Card>
    <Card title="报表归档" extra={<Button onClick={() => void records.refetch()}>刷新</Button>}>
      <ErrorNotice error={records.error}/>
      <Table rowKey="id" size="small" pagination={false} loading={records.isFetching} dataSource={records.data || []} columns={[
        {title: '报告', render: (_, row) => row.unavailable ? '权限已变更' : row.report_title},
        {title: '统计期间', render: (_, row) => row.period_start ? row.period_start + ' 至 ' + row.period_end : '—'},
        {title: '操作', render: (_, row) => !row.unavailable && <Button type="link" onClick={() => setDetail(row)}>查看</Button>},
      ]}/>
      <Space style={{marginTop: 12}}>
        <Button disabled={!before || records.isFetching} onClick={() => setBefore(undefined)}>返回最新</Button>
        <Button disabled={records.data?.length !== pagination || records.isFetching}
          onClick={() => setBefore(records.data?.at(-1)?.id)}>查看更多</Button>
      </Space>
    </Card>
    <DetailDrawer title={detail?.report_title || '报告'} data={detail ? summarize(detail) : null} onClose={() => setDetail(undefined)}/>
  </Space>
}
