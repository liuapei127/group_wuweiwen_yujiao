import {useState} from 'react'
import {useSearchParams} from 'react-router-dom'
import {Button, Card, Select, Space, Table, Tag} from 'antd'
import {useQuery} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ActionModal, ErrorNotice, PageTitle, type ActionSpec, type Field} from '../components/shared'
import {api, query} from '../lib/api'

export type Progress = {
  id: number; target_school: string; target_major: string | null; stage: string; progress_detail: string | null
  deadline: string | null; next_action: string | null; update_time: string
}
type Student = {id: number; real_name: string; student_no: string | null}
const endpoint = '/api/v1/student-admin/application-progress'
const pageSize = 20
const stageNames: Record<string, string> = {
  document_prep: '材料准备', submitted: '已提交', under_review: '审核中', offer_received: '已获录取',
  visa_processing: '签证办理', enrolled: '已入学',
}
const fields: Field[] = [
  {name: 'target_school', label: '目标院校', required: true},
  {name: 'target_major', label: '专业'},
  {name: 'stage', label: '阶段', kind: 'select', required: true, initial: 'document_prep',
    options: Object.entries(stageNames).map(([value, label]) => ({value, label}))},
  {name: 'deadline', label: '截止日期', kind: 'date'},
  {name: 'next_action', label: '下一步'},
  {name: 'progress_detail', label: '进度说明', kind: 'textarea'},
]
const columns = [
  {title: '院校', dataIndex: 'target_school'}, {title: '专业', dataIndex: 'target_major'},
  {title: '阶段', dataIndex: 'stage', render: (stage: string) => <Tag>{stageNames[stage] || stage}</Tag>},
  {title: '进度说明', dataIndex: 'progress_detail'}, {title: '下一步', dataIndex: 'next_action'},
  {title: '截止日期', dataIndex: 'deadline'},
]

export function ProgressTable({rows, loading, onEdit}: {rows?: Progress[]; loading: boolean; onEdit?: (row: Progress) => void}) {
  return <Table<Progress> size="small" rowKey="id" dataSource={rows || []} loading={loading} pagination={false}
    scroll={{x: 750}} locale={{emptyText: '暂无申请记录'}} columns={onEdit ? [
      ...columns, {title: '操作', render: (_, row) => <Button type="link" onClick={() => onEdit(row)}>更新进度</Button>},
    ] : columns}/>
}

export function ProgressPager({before, rows, move}: {before?: number; rows?: Progress[]; move: (value?: number) => void}) {
  return <Space style={{marginTop: 12}}>
    <Button disabled={!before} onClick={() => move()}>返回最新</Button>
    <Button disabled={rows?.length !== pageSize} onClick={() => move(rows?.at(-1)?.id)}>查看更多</Button>
  </Space>
}

export function ApplicationProgress() {
  const {user, can} = useAuth()
  const [params] = useSearchParams()
  const [selected, select] = useState<number>()
  const [before, move] = useState<number>()
  const [action, setAction] = useState<ActionSpec | null>(null)
  const students = useQuery({
    queryKey: [user?.id, 'application-students'], queryFn: () => api<Student[]>(endpoint + '/students'),
  })
  const studentId = selected ?? (Number(params.get('student_id')) || students.data?.[0]?.id)
  const records = useQuery({
    queryKey: [user?.id, 'application-records', studentId, before], enabled: studentId !== undefined,
    queryFn: () => api<Progress[]>(endpoint + '/' + studentId + query({before_id: before, limit: pageSize})),
  })

  function open(row?: Progress) {
    if (studentId === undefined) return
    const base = endpoint + '/' + studentId
    setAction({
      title: row ? '更新申请进度' : '新增申请进度', path: row ? base + '/' + row.id : base,
      method: row ? 'PUT' : 'POST', fields, initial: row,
      transform: values => ({
        target_school: values.target_school, target_major: values.target_major || null, stage: values.stage,
        deadline: values.deadline || null, next_action: values.next_action || null,
        progress_detail: values.progress_detail || null,
      }),
    })
  }

  return <>
    <PageTitle title="留学申请进度" description="维护企业授权范围内学生的办理阶段和下一步。"
      extra={can('applications:write') && <Button type="primary" disabled={!studentId} onClick={() => open()}>新增申请进度</Button>}/>
    <ErrorNotice error={students.error}/>
    <ErrorNotice error={records.error}/>
    <Card>
      <Select aria-label="选择学生" value={studentId} loading={students.isFetching} placeholder="暂无授权学生"
        options={(students.data || []).map(student => ({value: student.id,
          label: student.real_name + ' · ' + (student.student_no || student.id)}))}
        showSearch={{optionFilterProp: 'label'}} onChange={value => {select(value); move(undefined)}} style={{minWidth: 230}}/>
      <div style={{marginTop: 16}}><ProgressTable rows={records.data} loading={records.isFetching}
        onEdit={can('applications:write') ? open : undefined}/></div>
      <ProgressPager before={before} rows={records.data} move={move}/>
    </Card>
    <ActionModal action={action} onClose={() => setAction(null)} onSuccess={() => move(undefined)}/>
  </>
}
