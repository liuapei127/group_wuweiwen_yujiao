import {useState} from 'react'
import {App, Button, Card, Input, Select, Space, Table} from 'antd'
import {useQuery} from '@tanstack/react-query'
import {useSearchParams} from 'react-router-dom'
import {useAuth} from '../auth'
import {api, query, type Row} from '../lib/api'
import {studyStages, studyStageOptions} from '../lib/studyStages'
import {ActionModal, DetailDrawer, ErrorNotice, PageTitle, type ActionSpec, type Field} from '../components/shared'
import {teachingRoot, type Course} from './TeachingCourses'

export function TeachingScores() {
  const {user, can} = useAuth()
  const {message} = App.useApp()
  const [params] = useSearchParams()
  const [choice, choose] = useState<number>()
  const [semester, setSemester] = useState('')
  const [stage, setStage] = useState<string>()
  const [action, setAction] = useState<ActionSpec | null>(null)
  const [history, showHistory] = useState<unknown>()
  const students = useQuery({
    queryKey: [user?.id, 'authorized-students'],
    queryFn: () => api<Row[]>('/api/v1/portal/students'),
  })
  const studentId = choice ?? (Number(params.get('student_id')) || students.data?.[0]?.id)
  const courses = useQuery({
    queryKey: [user?.id, 'student-courses', studentId], enabled: !!studentId,
    queryFn: () => api<Course[]>(teachingRoot + '/students/' + studentId + '/courses'),
  })
  const scores = useQuery({
    queryKey: [user?.id, 'scores', studentId, semester], enabled: !!studentId,
    queryFn: () => api<Row[]>('/api/v1/enterprise/scores' + query({student_id: studentId, semester, limit: 100})),
  })
  function edit(row?: Row) {
    if (!studentId) return
    const courseOptions = (courses.data ?? []).map(course => ({
      value: course.id, label: course.name + ' · ' + studyStages[course.study_stage],
    }))
    if (row?.course_id && !courseOptions.some(course => course.value === row.course_id)) {
      courseOptions.push({value: row.course_id, label: row.course_name})
    }
    const fields: Field[] = [
      row && !row.course_id
        ? {name: 'course_name', label: '历史课程名称', required: true}
        : {name: 'course_id', label: '班级课程', kind: 'select', required: true, options: courseOptions},
      {name: 'score', label: '成绩', kind: 'number', required: true, min: 0, max: 999.99, precision: 2},
      {name: 'semester', label: '学期', required: true},
      {name: 'credit', label: '学分', kind: 'number', max: 99.9, precision: 1},
    ]
    if (row && !row.course_id) fields.splice(1, 0, {
      name: 'study_stage', label: '教学阶段', kind: 'select', required: true,
      options: [...studyStageOptions, {value: 'unspecified', label: '历史记录待核对'}],
    })
    if (row) fields.push(
      {name: 'expected_version', label: '当前版本', kind: 'number', disabled: true, required: true},
      {name: 'correction_reason', label: '更正原因', kind: 'textarea', required: true},
    )
    setAction({
      title: row ? '更正成绩' : '录入成绩',
      path: '/api/v1/enterprise/scores' + (row ? '/' + row.id : ''), method: row ? 'PUT' : 'POST',
      fields, initial: row ?? {semester},
      transform: values => ({...values, student_id: studentId}),
    })
  }
  async function viewHistory(id: number) {
    try {showHistory(await api('/api/v1/enterprise/scores/' + id + '/history'))}
    catch (error) {void message.error((error as Error).message)}
  }
  return <>
    <PageTitle title="学生成绩" description="按班级课程录入三个阶段的成绩，更正保留原因、版本和历史。"
      extra={can('scores:write') && <Button type="primary" disabled={!studentId || !courses.data?.length}
        onClick={() => edit()}>录入成绩</Button>}/>
    <ErrorNotice error={students.error || scores.error || courses.error}/>
    <Card>
      <Space wrap style={{marginBottom: 16}}>
        <Select aria-label="选择授权学生" value={studentId} style={{minWidth: 230}} onChange={choose}
          showSearch={{optionFilterProp: 'label'}}
          options={(students.data ?? []).map(row => ({value: row.id, label: row.real_name + ' · ' + (row.student_no ?? row.id)}))}/>
        <Input placeholder="筛选学期" value={semester} onChange={event => setSemester(event.target.value)}/>
        <Select aria-label="成绩教学阶段" placeholder="全部教学阶段" allowClear value={stage} onChange={setStage}
          style={{minWidth: 180}} options={Object.entries(studyStages).map(([value, label]) => ({value, label}))}/>
      </Space>
      {!courses.isFetching && studentId && !courses.data?.length && <p>当前班级尚未安排有效课程，请联系管理员安排课程。</p>}
      <Table<Row> rowKey="id" dataSource={(scores.data ?? []).filter(row => !stage || row.study_stage === stage)}
        loading={scores.isFetching} columns={[
          {title: '课程', dataIndex: 'course_name'},
          {title: '阶段', render: (_, row) => studyStages[row.study_stage ?? 'unspecified']},
          {title: '成绩', dataIndex: 'score'}, {title: '学期', dataIndex: 'semester'},
          {title: '学分', dataIndex: 'credit'}, {title: '版本', dataIndex: 'version'},
          {title: '操作', render: (_, row) => <Space>
            <Button type="link" onClick={() => void viewHistory(row.id)}>更正历史</Button>
            {can('scores:write') && <Button type="link" onClick={() => edit(row)}>更正</Button>}
          </Space>},
        ]}/>
    </Card>
    <ActionModal action={action} onClose={() => setAction(null)}/>
    <DetailDrawer title="成绩更正历史" data={history} onClose={() => showHistory(undefined)}/>
  </>
}
