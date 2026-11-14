import {useState} from 'react'
import {Button, Card, Form, Input, Segmented, Space, Table, Tabs, Typography} from 'antd'
import {useMutation, useQuery} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ErrorNotice, PageTitle} from '../components/shared'
import {api, query} from '../lib/api'
import {ReportSchedules} from './ReportSchedules'

type Operations = {
  department: string | null; leads_by_status: Record<string, number>; complaints_by_status: Record<string, number>
}
type Daily = {
  department: string | null; submitted_employee_days: number
  days: {report_date: string; submitted_employees: number}[]
}
type Period = {start: string; end: string}
const names: Record<string, string> = {
  new: '新线索', contacting: '联系中', qualified: '已确认意向', signed: '已签约', lost: '已流失',
  pending: '待处理', processing: '处理中', resolved: '已解决', closed: '已关闭',
}
function dateToday() {
  return new Intl.DateTimeFormat('en-CA', {timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit'}).format(new Date())
}

export function Reporting() {
  const {can} = useAuth()
  return <>
    <PageTitle title="业务报表" description="按授权范围查看经营、投诉和员工日报统计。"/>
    <Tabs items={[
      ...(can('reports:operations:read') ? [{key: 'ops', label: '经营与投诉', children: <OperationalReport/>}] : []),
      ...(can('reports:summary:read') ? [{key: 'daily', label: '日报提交', children: <DailyReport/>}] : []),
      {key: 'plans', label: '计划与归档', children: <ReportSchedules/>},
    ]}/>
  </>
}

function OperationalReport() {
  const {user} = useAuth()
  const today = dateToday()
  const [period, setPeriod] = useState<Period>({start: today.slice(0, 8) + '01', end: today})
  const result = useQuery({
    queryKey: [user?.id, 'operations', period],
    queryFn: () => api<Operations>('/api/v1/reporting/operations' + query(period)),
  })
  return <Space orientation="vertical" size="middle" style={{width: '100%'}}>
    <Form layout="inline" initialValues={period} onFinish={setPeriod}>
      <Form.Item name="start" label="开始日期" rules={[{required: true}]}><Input type="date"/></Form.Item>
      <Form.Item name="end" label="结束日期" rules={[{required: true}]}><Input type="date"/></Form.Item>
      <Form.Item><Button type="primary" htmlType="submit">查询统计</Button></Form.Item>
    </Form>
    <ErrorNotice error={result.error}/>
    <Typography.Text>范围：{result.data ? (result.data.department ?? '全公司') : '—'}</Typography.Text>
    <Card title="期间创建的 CRM 线索"><StatusCounts values={result.data?.leads_by_status} loading={result.isFetching}/></Card>
    <Card title="期间提交的投诉"><StatusCounts values={result.data?.complaints_by_status} loading={result.isFetching}/></Card>
  </Space>
}

function StatusCounts({values, loading}: {values?: Record<string, number>; loading: boolean}) {
  return <Table rowKey="status" size="small" pagination={false} loading={loading}
    dataSource={Object.entries(values || {}).map(([status, count]) => ({status, count}))} columns={[
      {title: '当前状态', render: (_, row) => names[row.status] || row.status},
      {title: '数量', dataIndex: 'count'},
    ]}/>
}

function DailyReport() {
  const {user, can} = useAuth()
  const [anchor, date] = useState(dateToday)
  const [period, setPeriod] = useState('week')
  const result = useQuery({
    queryKey: [user?.id, 'report-submissions', anchor, period], enabled: !!anchor,
    queryFn: () => api<Daily>('/api/v1/reporting/employee-reports/summary' + query({anchor, period})),
  })
  const formal = useMutation({
    mutationFn: () => api<{sections: Record<string, string>}>('/api/v1/reporting/employee-reports/formal-summary', {
      method: 'POST', body: {anchor, report_kind: period === 'day' ? 'daily' : 'weekly'},
    }),
  })
  const sections = [
    ['work_summary', '工作总结'],
    ['key_progress_summary', '关键进展'],
    ['risk_summary', '风险事项'],
    ['next_work_suggestions', '下一步建议'],
  ]
  return <Card>
    <Space wrap>
      <Input aria-label="统计日期" type="date" value={anchor} onChange={e => {date(e.target.value); formal.reset()}}/>
      <Segmented options={[{label: '按日', value: 'day'}, {label: '按周', value: 'week'}]}
        value={period} onChange={value => {setPeriod(value); formal.reset()}}/>
      {can('reports:formal:generate') && <Button disabled={!anchor} loading={formal.isPending} onClick={() => formal.mutate()}>生成 AI 总结</Button>}
      {result.data && <Typography.Text>累计提交 {result.data.submitted_employee_days} 人次</Typography.Text>}
    </Space>
    <ErrorNotice error={result.error}/>
    <ErrorNotice error={formal.error}/>
    {formal.data && <Card title="员工正式报告 AI 总结" style={{marginTop: 16}}>
      {sections.map(([key, label]) => <section key={key}>
        <Typography.Title level={5}>{label}</Typography.Title>
        <Typography.Paragraph style={{whiteSpace: 'pre-wrap'}}>{formal.data.sections[key]}</Typography.Paragraph>
      </section>)}
    </Card>}
    <Table rowKey="report_date" size="small" pagination={false} loading={result.isFetching}
      dataSource={result.data?.days || []} style={{marginTop: 16}} columns={[
        {title: '日期', dataIndex: 'report_date'}, {title: '提交人数', dataIndex: 'submitted_employees'},
      ]}/>
  </Card>
}
