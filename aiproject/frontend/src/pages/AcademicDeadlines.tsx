import {Alert, Button, Card, Segmented, Select, Space, Table, Tag} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {useState} from 'react'
import {useSearchParams} from 'react-router-dom'
import {studyStages, studyStageOptions} from '../lib/studyStages'
import {useAuth} from '../auth'
import {api, query} from '../lib/api'
import {ActionModal, ErrorNotice, PageTitle, type ActionSpec} from '../components/shared'

type Request = <T>(path: string, method?: string, body?: unknown) => Promise<T>
type Deadline = {
  id: number; title: string; deadline_type: string; description: string | null
  deadline: string; status: string; shared: boolean; reminder_enabled: boolean; due_soon: boolean
  study_stage: string
}
type DeadlinePage = {items: Deadline[]; has_more: boolean}
const types: Record<string, string> = {paper: '论文', exam: '考试', application: '申请', visa: '签证', other: '其他'}
const statuses: Record<string, string> = {pending: '待办理', reminded: '待办理', done: '已完成', missed: '已错过'}
export const academicDeadlineEndpoint = '/api/v1/student/deadlines'
const pageSize = 20

export function AcademicDeadlines({request}: {request: Request}) {
  const [upcoming, setUpcoming] = useState(true)
  const [offset, setOffset] = useState(0)
  const cache = useQueryClient()
  const key = ['visitor', 'student', 'deadlines']
  const records = useQuery({
    queryKey: [...key, upcoming, offset],
    queryFn: () => request<DeadlinePage>(academicDeadlineEndpoint + '?upcoming=' + upcoming + '&offset=' + offset + '&limit=' + pageSize),
    staleTime: 0,
    refetchOnWindowFocus: true,
  })
  const complete = useMutation({
    mutationFn: (id: number) => request<Deadline>(academicDeadlineEndpoint + '/' + id + '/complete', 'POST'),
    onSuccess: () => {
      setOffset(0)
      return cache.invalidateQueries({queryKey: key})
    },
  })
  return <Card title="我的考务">
    <Space orientation="vertical" size="middle" style={{width: '100%'}}>
      <Segmented value={upcoming ? 'soon' : 'all'}
        options={[{label: '近七天待办', value: 'soon'}, {label: '全部考务', value: 'all'}]}
        onChange={value => {setOffset(0); setUpcoming(value === 'soon')}}/>
      {(records.error || complete.error) && <Alert type="error" showIcon
        title={(records.error || complete.error)?.message}/>}
      <Table<Deadline> rowKey="id" dataSource={records.data?.items || []} loading={records.isFetching}
        pagination={false} scroll={{x: 740}}
        locale={{emptyText: upcoming ? '未来七天暂无开启提醒的考务待办' : '暂无考务记录'}} columns={[
          {title: '事项', render: (_, row) => <>{row.title}{row.shared && <> <Tag>通用</Tag></>}</>},
          {title: '类型', render: (_, row) => types[row.deadline_type] || row.deadline_type},
          {title: '教学阶段', render: (_, row) => studyStages[row.study_stage]},
          {title: '说明', dataIndex: 'description'},
          {title: '截止时间（北京时间）', render: (_, row) => row.deadline.slice(0, 16).replace('T', ' ')},
          {title: '状态', render: (_, row) => <Tag color={row.due_soon ? 'orange' : undefined}>
            {row.due_soon ? '即将截止' : statuses[row.status] || row.status}
          </Tag>},
          {title: '操作', render: (_, row) => !row.shared && ['pending', 'reminded'].includes(row.status) &&
            <Button type="link" loading={complete.isPending && complete.variables === row.id}
              disabled={complete.isPending} onClick={() => complete.mutate(row.id)}>标记完成</Button>},
        ]}/>
      <Space>
        <Button disabled={!offset || records.isFetching} onClick={() => setOffset(value => value - pageSize)}>上一页</Button>
        <Button disabled={!records.data?.has_more || offset >= 10000 || records.isFetching}
          onClick={() => setOffset(value => value + pageSize)}>下一页</Button>
      </Space>
    </Space>
  </Card>
}


const staffEndpoint = '/api/v1/student-admin/academic-deadlines'

export function StaffDeadlines() {
  const {user, can} = useAuth()
  const [params] = useSearchParams()
  const [classId, setClassId] = useState<number>()
  const [selected, select] = useState<number>()
  const [offset, setOffset] = useState(0)
  const [action, setAction] = useState<ActionSpec | null>(null)
  const students = useQuery({
    queryKey: [user?.id, 'academic-students'],
    queryFn: () => api<{id: number; real_name: string; student_no: string | null}[]>(staffEndpoint + '/students'),
  })
  const classes = useQuery({
    queryKey: [user?.id, 'my-classes'], enabled: can('students:read'),
    queryFn: () => api<{id: number; name: string; project_name: string}[]>('/api/v1/teacher/classes'),
  })
  const id = selected ?? (Number(params.get('student_id')) || students.data?.[0]?.id)
  const deadlines = useQuery({
    queryKey: [user?.id, 'academic-deadlines', id, offset], enabled: id !== undefined,
    queryFn: () => api<DeadlinePage>(staffEndpoint + '/' + id + query({offset, limit: pageSize})),
  })
  function openEditor(row?: Deadline, wholeClass = false) {
    const path = staffEndpoint + '/' + id
    const requestId = crypto.randomUUID()
    setAction({
      title: wholeClass ? '向班级发布考务' : row ? '更正考务' : '新增考务',
      path: wholeClass ? staffEndpoint + '/classes/' + classId + '/batch' : row ? path + '/' + row.id : path,
      method: row ? 'PUT' : 'POST',
      initial: row && {...row, deadline: row.deadline.slice(0, 16), reminder_enabled: row.reminder_enabled ? 'on' : 'off'},
      fields: [
        {name: 'title', label: '事项名称', required: true},
        {name: 'deadline_type', label: '类型', kind: 'select', required: true,
          options: Object.entries(types).map(([value, label]) => ({value, label}))},
        {name: 'study_stage', label: '教学阶段', kind: 'select', required: true,
          options: row?.study_stage === 'unspecified'
            ? [...studyStageOptions, {value: 'unspecified', label: '历史记录待核对'}] : studyStageOptions},
        {name: 'deadline', label: '截止时间（北京时间）', kind: 'datetime-local', required: true},
        {name: 'description', label: '说明', kind: 'textarea'},
        {name: 'reminder_enabled', label: '近七天提醒', kind: 'select', initial: 'on', required: true,
          options: [{value: 'on', label: '开启'}, {value: 'off', label: '关闭'}]},
      ],
      transform: values => ({...values, reminder_enabled: values.reminder_enabled === 'on',
        ...(wholeClass ? {request_id: requestId} : {})}),
    })
  }

  return <>
    <PageTitle title="考务管理" description="为授权学生记录考试、论文和其他截止事项。"
      extra={can('academics:write') && <Space>
        <Button type="primary" disabled={id === undefined} onClick={() => openEditor()}>新增考务</Button>
        <Select aria-label="发布考务的班级" placeholder="选择班级" value={classId} onChange={setClassId}
          style={{minWidth: 180}} options={(classes.data ?? []).map(row => ({value: row.id, label: row.project_name + ' · ' + row.name}))}/>
        <Button disabled={!classId} onClick={() => openEditor(undefined, true)}>向班级发布</Button>
      </Space>}/>
    <ErrorNotice error={students.error}/><ErrorNotice error={deadlines.error}/>
    <Card>
      <Select aria-label="考务学生" value={id} loading={students.isFetching} placeholder="暂无授权学生"
        options={(students.data || []).map(student => ({value: student.id,
          label: student.real_name + ' · ' + (student.student_no || student.id)}))}
        showSearch={{optionFilterProp: 'label'}} onChange={value => {select(value); setOffset(0)}} style={{minWidth: 230}}/>
      <Table<Deadline> rowKey="id" dataSource={deadlines.data?.items || []} loading={deadlines.isFetching}
        pagination={false} scroll={{x: 540}} style={{marginTop: 16}} locale={{emptyText: '暂无考务记录'}} columns={[
          {title: '事项', render: (_, row) => <>{row.title}{row.shared && <> <Tag>通用</Tag></>}</>},
          {title: '类型', render: (_, row) => types[row.deadline_type] || row.deadline_type},
          {title: '教学阶段', render: (_, row) => studyStages[row.study_stage]},
          {title: '截止（北京时间）', render: (_, row) => row.deadline.slice(0, 16).replace('T', ' ')},
          {title: '状态', render: (_, row) => statuses[row.status] || row.status},
          {title: '操作', render: (_, row) => can('academics:write') && !row.shared && ['pending', 'reminded'].includes(row.status) &&
            <Button type="link" onClick={() => openEditor(row)}>更正</Button>},
        ]}/>
      <Space style={{marginTop: 12}}>
        <Button disabled={!offset || deadlines.isFetching} onClick={() => setOffset(value => value - pageSize)}>上一页</Button>
        <Button disabled={!deadlines.data?.has_more || offset >= 10000 || deadlines.isFetching}
          onClick={() => setOffset(value => value + pageSize)}>下一页</Button>
      </Space>
    </Card>
    <ActionModal action={action} onClose={() => setAction(null)} onSuccess={() => setOffset(0)}/>
  </>
}
