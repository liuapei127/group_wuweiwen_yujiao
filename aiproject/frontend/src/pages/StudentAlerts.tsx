import {useState} from 'react'
import {Button, Card, Input, Select, Space, Table, Tag} from 'antd'
import {useSearchParams} from 'react-router-dom'
import {useQuery} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ActionModal, ErrorNotice, PageTitle, type ActionSpec} from '../components/shared'
import {api, query} from '../lib/api'
import {ReportSchedules} from './ReportSchedules'

type Alert = {
  id: number; student_id: number; student_name?: string | null; teacher_id: number | null; risk_level: string; status: string
  trigger_reason: string; follow_record: string | null; create_time: string
}
const endpoint = '/api/v1/student-admin/psych-alerts'
const statuses: Record<string, string> = {pending: '待跟进', following: '跟进中', resolved: '已结案', dismissed: '已排除'}
const levels: Record<string, string> = {low: '低', medium: '中', high: '高'}

export function StudentAlerts() {
  const {user, can} = useAuth()
  const [params] = useSearchParams()
  const [studentId, selectStudent] = useState<number | undefined>(() => Number(params.get('student_id')) || undefined)
  const [before, setBefore] = useState<number>()
  const [action, setAction] = useState<ActionSpec | null>(null)
  const mayWrite = can('student-alerts:write')
  const [week, setWeek] = useState(() => new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit',
  }).format(new Date()))
  const students = useQuery({
    queryKey: [user?.id, 'student-alert-students'],
    queryFn: () => api<{id: number; real_name: string}[]>(endpoint + '/students'),
  })
  const weekly = useQuery({
    queryKey: [user?.id, 'student-alert-weekly', week], enabled: !!week,
    queryFn: () => api<{period_start: string; period_end: string;
      items: {status: string; risk_level: string; count: number}[]}>(endpoint + '/weekly' + query({anchor: week})),
  })
  const records = useQuery({
    queryKey: [user?.id, 'student-alerts', before, studentId],
    queryFn: () => api<Alert[]>(endpoint + query({before_id: before, limit: 20, student_id: studentId})),
  })
  return <>
    <PageTitle title="心理预警" description="查看分派给你的预警，以及授权范围内待分派的预警。"
      extra={mayWrite && <Button type="primary" disabled={!students.data?.length} onClick={() => setAction({
        title: '登记心理预警', path: endpoint, method: 'POST', fields: [
          {name: 'student_id', label: '学生', kind: 'select', required: true,
            options: (students.data || []).map(row => ({value: row.id, label: row.real_name + ' · ' + row.id}))},
          {name: 'risk_level', label: '风险等级', kind: 'select', required: true,
            options: Object.entries(levels).map(([value, label]) => ({value, label}))},
          {name: 'trigger_reason', label: '观察说明', kind: 'textarea', required: true},
        ],
      })}>登记预警</Button>}/>
    <ErrorNotice error={students.error}/>
    <Card title="心理预警周统计" style={{marginBottom: 16}}>
      <Input type="date" aria-label="预警统计日期" value={week} onChange={event => setWeek(event.target.value)}/>
      <ErrorNotice error={weekly.error}/>
      {weekly.data && <p>{weekly.data.period_start} 至 {weekly.data.period_end}</p>}
      <Table rowKey={row => row.status + ':' + row.risk_level} size="small" pagination={false}
        loading={weekly.isFetching} dataSource={weekly.data?.items || []} columns={[
          {title: '状态', render: (_, row) => statuses[row.status] || row.status},
          {title: '等级', render: (_, row) => levels[row.risk_level] || row.risk_level},
          {title: '数量', dataIndex: 'count'},
        ]}/>
    </Card>
    <ErrorNotice error={records.error}/>
    <Card>
      <Select aria-label="预警学生" placeholder="全部负责学生" allowClear value={studentId}
        style={{minWidth: 260, marginBottom: 16}} showSearch={{optionFilterProp: 'label'}}
        options={(students.data ?? []).map(student => ({value: student.id, label: student.real_name + ' · ' + student.id}))}
        onChange={value => {selectStudent(value); setBefore(undefined)}}/>
      <Table<Alert> rowKey="id" pagination={false} loading={records.isFetching} dataSource={records.data || []}
        scroll={{x: 780}} locale={{emptyText: '暂无可查看的预警'}} columns={[
          {title: '学生编号', dataIndex: 'student_id', width: 130},
          {title: '姓名', dataIndex: 'student_name', width: 120, render: value => value || '—'},
          {title: '风险等级', render: (_, row) => <Tag color={row.risk_level === 'high' ? 'red' : undefined}>{levels[row.risk_level]}</Tag>},
          {title: '原因', dataIndex: 'trigger_reason'},
          {title: '跟进记录', dataIndex: 'follow_record', render: value => <span style={{whiteSpace: 'pre-wrap'}}>{value || '—'}</span>},
          {title: '状态', render: (_, row) => row.teacher_id === null ? <Tag color="orange">待分派</Tag> : statuses[row.status]},
          {title: '操作', render: (_, row) => can('student-alerts:write') && ['pending', 'following'].includes(row.status) &&
            <Button type="link" onClick={() => setAction({
              title: '记录预警跟进', path: endpoint + '/' + row.id, method: 'PUT', fields: [
                {name: 'status', label: '跟进状态', kind: 'select', required: true, initial: 'following',
                  options: ['following', 'resolved', 'dismissed'].map(value => ({value, label: statuses[value]}))},
                {name: 'follow_record', label: '本次跟进记录', kind: 'textarea', required: true},
              ],
            })}>{row.teacher_id === null ? '接手并跟进' : '记录跟进'}</Button>},
        ]}/>
      <Space style={{marginTop: 12}}>
        <Button disabled={!before || records.isFetching} onClick={() => setBefore(undefined)}>返回最新</Button>
        <Button disabled={records.data?.length !== 20 || records.isFetching} onClick={() => setBefore(records.data?.at(-1)?.id)}>查看更多</Button>
      </Space>
    </Card>
    <div style={{marginTop: 16}}><ReportSchedules/></div>
    <ActionModal action={action} onClose={() => setAction(null)}/>
  </>
}
