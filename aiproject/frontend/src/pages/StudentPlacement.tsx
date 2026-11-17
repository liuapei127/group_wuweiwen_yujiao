import {useState} from 'react'
import {App, Button, Card, Input, Modal, Select, Space, Table} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {api, query} from '../lib/api'
import {ErrorNotice} from '../components/shared'
import {classroomsEndpoint, classroomsQuery, type Classroom, type Project} from './ClassManagement'

type Student = {id: number; real_name: string; class_id: number | null; class_name: string | null; project_name: string | null}

export function StudentPlacement() {
  const cache = useQueryClient()
  const {message} = App.useApp()
  const [keyword, setKeyword] = useState('')
  const [offset, setOffset] = useState(0)
  const [targets, setTargets] = useState<Student[]>([])
  const [selection, setSelection] = useState<Student[]>([])
  const selected = targets[0]
  const [projectId, setProjectId] = useState<number>()
  const [classId, setClassId] = useState<number>()
  const [reason, setReason] = useState('')
  const students = useQuery({
    queryKey: [...classroomsQuery, 'placement-students', keyword, offset],
    queryFn: () => api<{items: Student[]; has_more: boolean}>(classroomsEndpoint + '/students' + query({keyword, offset})),
  })
  const projects = useQuery({
    queryKey: [...classroomsQuery, 'enrollment-projects'], enabled: !!selected,
    queryFn: () => api<Project[]>(classroomsEndpoint + '/enrollment-projects'),
  })
  const classes = useQuery({
    queryKey: [...classroomsQuery, 'enrollment-classes', projectId], enabled: !!selected && !!projectId,
    queryFn: () => api<Classroom[]>(classroomsEndpoint + '/enrollment-projects/' + projectId + '/classes'),
  })
  const save = useMutation({
    mutationFn: () => api(classroomsEndpoint + '/student-placements' + (targets.length > 1 ? '/batch' : ''), {method: 'POST', body: {
      project_id: projectId, class_id: classId, reason: reason.trim(),
      ...(targets.length > 1 ? {students: targets.map(student => ({student_id: student.id, expected_class_id: student.class_id}))}
        : {student_id: selected!.id, expected_class_id: selected!.class_id}),
    }}),
    onSuccess: () => {
      setTargets([])
      setSelection([])
      void cache.invalidateQueries()
      void message.success('入班信息已保存，未完成事项已按班主任归属交接')
    },
  })
  function open(rows: Student[]) {
    save.reset(); setClassId(undefined); setProjectId(undefined); setReason(''); setTargets(rows)
  }
  return <Card title="学生入班与转班" style={{marginTop: 16}}>
    <Space wrap style={{marginBottom: 12}}>
    <Input.Search placeholder="搜索学生姓名或学号" aria-label="搜索待入班学生" allowClear
      style={{maxWidth: 300}} onSearch={value => {setKeyword(value.trim()); setOffset(0)}}/>
    <Button disabled={!selection.length || selection.length > 100}
      onClick={() => open(selection)}>批量安排（已选{selection.length}人）</Button>
    </Space>
    <ErrorNotice error={students.error}/>
    <Table<Student> rowKey="id" dataSource={students.data?.items ?? []} loading={students.isFetching} pagination={false}
      rowSelection={{selectedRowKeys: selection.map(student => student.id), preserveSelectedRowKeys: true,
        onChange: (_, rows) => setSelection(rows)}}
      columns={[
        {title: '学生', dataIndex: 'real_name'}, {title: '项目', render: (_, row) => row.project_name ?? '待确认'},
        {title: '班级', render: (_, row) => row.class_name ?? '待入班'},
        {title: '操作', render: (_, row) => <Button type="link" onClick={() => open([row])}>{row.class_id ? '转班' : '安排入班'}</Button>},
      ]}/>
    <Space style={{marginTop: 12}}>
      <Button disabled={!offset || students.isFetching} onClick={() => setOffset(value => value - 20)}>上一页</Button>
      <Button disabled={!students.data?.has_more || students.isFetching} onClick={() => setOffset(value => value + 20)}>下一页</Button>
    </Space>
    <Modal title={targets.length > 1 ? targets.length + '名学生 · 批量入班安排' : selected ? selected.real_name + ' · 入班安排' : '入班安排'} open={!!selected}
      onCancel={() => {if (!save.isPending) setTargets([])}} confirmLoading={save.isPending}
      okButtonProps={{disabled: !classId || !projectId || !reason.trim()}} onOk={() => save.mutate()}>
      <Space orientation="vertical" style={{width: '100%'}}>
        {targets.length > 1 && <p>统一安排至以下班级。任何学生状态或班级已变化时，整批不保存，请刷新名单后重试。</p>}
        <Select aria-label="入班项目" placeholder="选择项目" value={projectId} style={{width: '100%'}}
          options={(projects.data ?? []).map(row => ({value: row.id, label: row.project_name}))}
          onChange={value => {setProjectId(value); setClassId(undefined)}}/>
        <Select aria-label="入班班级" placeholder="选择班级" value={classId} style={{width: '100%'}}
          disabled={!projectId} options={(classes.data ?? []).map(row => ({value: row.id, label: row.name + ' · ' + row.teacher_name}))}
          onChange={setClassId}/>
        <Input.TextArea aria-label="入班调整原因" placeholder="填写入班或转班原因" value={reason} maxLength={1000}
          onChange={event => setReason(event.target.value)}/>
        <ErrorNotice error={save.error || projects.error || classes.error}/>
      </Space>
    </Modal>
  </Card>
}
