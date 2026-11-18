import {useState} from 'react'
import {App, Button, Select, Typography} from 'antd'
import {api, download} from '../lib/api'
import {useAuth} from '../auth'
import {DetailDrawer, EntityTable, Status, options} from '../components/shared'

function useHistory() {
  const {message} = App.useApp()
  const [history, setHistory] = useState<unknown>()
  async function load(path: string) {
    try {setHistory(await api(path))}
    catch (error) {void message.error((error as Error).message)}
  }
  return {load, drawer: <DetailDrawer title="处理历史" data={history} onClose={() => setHistory(undefined)}/>}
}

export function Leaves() {
  const {can} = useAuth()
  const {message} = App.useApp()
  const [status, setStatus] = useState<string | undefined>('pending')
  const history = useHistory()
  return <>
    <EntityTable title="请假审批" endpoint="/api/v1/student-admin/leaves" recordPath="/api/v1/student-admin/leaves"
      description="查看分配给本人的请假及已处理记录。审批结果、学生通知和关联待办同步保存。"
      params={{status, limit: 100}} toolbar={<Select aria-label="请假状态" allowClear placeholder="全部状态" value={status}
        options={options(['pending', 'approved', 'rejected', 'cancelled'])} onChange={setStatus} style={{width: 160}}/>}
      columns={[
        {title: '请假单', dataIndex: 'id'}, {title: '学生编号', dataIndex: 'student_id'},
        {title: '姓名', dataIndex: 'student_name', render: value => value || '—'},
        {title: '类型', dataIndex: 'leave_type', render: value => ({sick: '病假', personal: '事假', emergency: '紧急事由'}[value as string] || value)},
        {title: '开始时间', dataIndex: 'start_time'}, {title: '结束时间', dataIndex: 'end_time'},
        {title: '原因', dataIndex: 'reason'}, {title: '状态', dataIndex: 'status', render: value => <Status value={value}/>},
        {title: '审批意见', dataIndex: 'approval_comment'}, {title: '审批时间', dataIndex: 'approval_time'},
      ]}
      rowActions={(row, open, show) => <>
        <Button type="link" onClick={() => show(row)}>详情</Button>
        <Button type="link" onClick={() => void history.load('/api/v1/student-admin/leaves/' + row.id + '/history')}>审批历史</Button>
        {row.attachment_url && <Button type="link" onClick={() => void download('/api/v1/student-admin/leaves/' + row.id + '/attachment', '请假证明')
          .catch((error: Error) => void message.error(error.message))}>查看证明</Button>}
        {can('leaves:approve') && row.status === 'pending' && ['approved', 'rejected'].map(decision => <Button key={decision} type="link"
          danger={decision === 'rejected'} onClick={() => open({
            title: decision === 'approved' ? '核对后同意请假' : '核对后拒绝请假',
            path: '/api/v1/student-admin/leaves/' + row.id + '/approve', method: 'POST', initial: {decision},
            formExtra: () => <Typography.Paragraph>请假单 #{row.id} · {row.student_name || row.student_id}<br/>
              {row.start_time} 至 {row.end_time}<br/>{row.reason}</Typography.Paragraph>,
            fields: [
              {name: 'decision', label: '审批决定', kind: 'select', required: true, disabled: true, options: options(['approved', 'rejected'])},
              {name: 'approval_comment', label: '审批意见', kind: 'textarea', max: 512, required: decision === 'rejected', help: '拒绝时必须说明原因，学生可查看。'},
            ],
          })}>{decision === 'approved' ? '同意' : '拒绝'}</Button>)}
      </>}/>
    {history.drawer}
  </>
}

export function Tickets() {
  const {can} = useAuth()
  const [status, setStatus] = useState<string>()
  const history = useHistory()
  const states = ['pending', 'processing', 'resolved', 'closed']
  const next: Record<string, string[]> = {pending: ['processing'], processing: ['resolved'], resolved: ['closed'], closed: []}
  return <>
    <EntityTable title="投诉工单" endpoint="/api/v1/enterprise/tickets" recordPath="/api/v1/enterprise/tickets"
      description="学习事务由指定班主任处理；服务与人员投诉由主管处理并保密。可查看但未分配给本人的记录仅供查阅。"
      params={{status, limit: 100}} toolbar={<Select aria-label="工单状态" allowClear placeholder="全部状态"
        options={options(states)} onChange={setStatus} style={{width: 160}}/>}
      columns={[
        {title: '工单', dataIndex: 'id'}, {title: '标题', dataIndex: 'title'}, {title: '学生编号', dataIndex: 'student_id'},
        {title: '姓名', dataIndex: 'student_name', render: value => value || '—'},
        {title: '受理渠道', dataIndex: 'category', render: value => value === 'company' ? '主管处理（保密）' : '班主任处理'},
        {title: '类型', dataIndex: 'ticket_type', render: value => ({complaint: '投诉', suggestion: '建议', consult: '咨询'}[value as string] || value)},
        {title: '状态', dataIndex: 'status', render: value => <Status value={value}/>},
        {title: '处理结果', dataIndex: 'solution'}, {title: '更新时间', dataIndex: 'update_time'},
      ]}
      rowActions={(row, open, show) => <>
        <Button type="link" onClick={() => show(row)}>详情</Button>
        <Button type="link" onClick={() => void history.load('/api/v1/enterprise/tickets/' + row.id + '/history')}>处理历史</Button>
        {can('tickets:write') && row.can_process === true && !!next[row.status]?.length && <Button type="link" onClick={() => open({
          title: '核对后处理工单', path: '/api/v1/enterprise/tickets/' + row.id, method: 'PATCH',
          initial: {expected_status: row.status, status: next[row.status][0], solution: row.solution},
          formExtra: () => <Typography.Paragraph>工单 #{row.id} · {row.student_name || row.student_id}<br/>{row.content}</Typography.Paragraph>,
          fields: [
            {name: 'expected_status', label: '当前状态', kind: 'select', disabled: true, required: true, options: options(states)},
            {name: 'status', label: '处理为', kind: 'select', required: true, options: options(next[row.status])},
            {name: 'solution', label: '处理说明', kind: 'textarea', required: row.status !== 'pending', help: '解决和关闭必须填写说明，结果会反馈给学生。'},
          ],
        })}>{row.status === 'pending' ? '受理' : row.status === 'processing' ? '提交处理结果' : '关闭'}</Button>}
      </>}/>
    {history.drawer}
  </>
}
