import {useState} from 'react'
import {App, Button, Card, Modal, Select, Space, Table, Tag} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {api, type Row} from '../lib/api'
import {studyStages, studyStageOptions} from '../lib/studyStages'
import {ActionModal, ErrorNotice, PageTitle, type ActionSpec} from '../components/shared'
import {classroomsEndpoint, type Classroom} from './ClassManagement'

export const teachingRoot = '/api/v1/teaching'
export type Course = {id: number; name: string; study_stage: string; institution: string | null; enabled: boolean}

export function TeachingCourses() {
  const cache = useQueryClient()
  const {message} = App.useApp()
  const [action, setAction] = useState<ActionSpec | null>(null)
  const [selected, select] = useState<number>()
  const [assignment, setAssignment] = useState<{classId: number; courseIds: number[]}>()
  const courses = useQuery({queryKey: ['teaching-courses'], queryFn: () => api<Course[]>(teachingRoot + '/courses')})
  const classes = useQuery({queryKey: ['teaching-classes'], queryFn: () => api<Classroom[]>(classroomsEndpoint)})
  const allocations = useQuery({
    queryKey: ['class-courses', selected], enabled: !!selected,
    queryFn: () => api<number[]>(teachingRoot + '/classes/' + selected + '/courses'),
  })
  const save = useMutation({
    mutationFn: () => api(teachingRoot + '/classes/' + assignment!.classId + '/courses', {
      method: 'PUT', body: {course_ids: assignment!.courseIds},
    }),
    onSuccess: () => {
      setAssignment(undefined)
      void cache.invalidateQueries({queryKey: ['class-courses']})
      void message.success('班级课程已保存')
    },
  })
  function edit(row?: Course) {
    setAction({
      title: row ? '编辑教学课程' : '新增教学课程',
      path: teachingRoot + '/courses' + (row ? '/' + row.id : ''), method: row ? 'PUT' : 'POST',
      initial: row ? {...row, enabled: row.enabled ? 'on' : 'off'} : {enabled: 'on'},
      fields: [
        {name: 'name', label: '课程名称', required: true},
        {name: 'study_stage', label: '教学阶段', kind: 'select', required: true, options: studyStageOptions},
        {name: 'institution', label: '授课院校或机构'},
        {name: 'enabled', label: '状态', kind: 'select', required: true,
          options: [{value: 'on', label: '开设'}, {value: 'off', label: '停开'}]},
      ],
      transform: (values: Row) => ({...values, enabled: values.enabled === 'on'}),
    })
  }
  return <>
    <PageTitle title="教学课程与开课安排" description="维护三个教学阶段的免费课程，并安排到班级，供班主任录入成绩。"
      extra={<Button type="primary" onClick={() => edit()}>新增教学课程</Button>}/>
    <ErrorNotice error={courses.error || classes.error || allocations.error}/>
    <Card>
      <Table<Course> rowKey="id" loading={courses.isFetching} dataSource={courses.data ?? []} columns={[
        {title: '课程', dataIndex: 'name'},
        {title: '教学阶段', render: (_, row) => studyStages[row.study_stage]},
        {title: '院校或机构', dataIndex: 'institution'},
        {title: '状态', render: (_, row) => <Tag>{row.enabled ? '开设' : '停开'}</Tag>},
        {title: '操作', render: (_, row) => <Button type="link" onClick={() => edit(row)}>编辑</Button>},
      ]}/>
    </Card>
    <Card title="班级开课安排" style={{marginTop: 16}}>
      <Space wrap>
        <Select aria-label="安排课程的班级" placeholder="选择班级" value={selected} onChange={select}
          showSearch={{optionFilterProp: 'label'}} style={{minWidth: 280}}
          options={(classes.data ?? []).map(row => ({value: row.id, label: row.project_name + ' · ' + row.name}))}/>
        <Button disabled={!selected || allocations.data === undefined} onClick={() => {
          save.reset(); setAssignment({classId: selected!, courseIds: allocations.data ?? []})
        }}>安排课程</Button>
      </Space>
      <p>{(courses.data ?? []).filter(row => allocations.data?.includes(row.id))
        .map(row => row.name + '（' + studyStages[row.study_stage] + '）').join('、') || '尚未安排课程'}</p>
    </Card>
    <Modal title="安排班级课程" open={!!assignment} confirmLoading={save.isPending}
      onCancel={() => {if (!save.isPending) setAssignment(undefined)}} onOk={() => save.mutate()}>
      <Select mode="multiple" aria-label="班级课程" value={assignment?.courseIds}
        options={(courses.data ?? []).map(row => ({value: row.id, label: row.name + ' · ' + studyStages[row.study_stage]}))}
        style={{width: '100%'}} onChange={courseIds => {if (assignment) setAssignment({...assignment, courseIds})}}/>
      <ErrorNotice error={save.error}/>
    </Modal>
    <ActionModal action={action} onClose={() => setAction(null)}/>
  </>
}
