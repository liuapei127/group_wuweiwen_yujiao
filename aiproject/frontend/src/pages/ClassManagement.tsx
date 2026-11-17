import {useState} from 'react'
import {App, Button, Card, Input, Modal, Select, Space, Switch, Table, Tag} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {ErrorNotice, PageTitle} from '../components/shared'
import {api, query} from '../lib/api'
import {StudentPlacement} from './StudentPlacement'

export const classroomsEndpoint = '/api/v1/enterprise/classrooms'
export const classroomsQuery = ['classrooms']

export type Project = {
  id: number
  project_name: string
  status: number
  abroad_country: 'Singapore' | 'Germany' | null
}

export type Classroom = {
  id: number
  project_id: number
  project_name: string
  name: string
  enabled: boolean
  student_count: number
  teacher_id: number
  teacher_name: string
}

export type Teacher = {id: number; real_name: string}
type Student = {id: number; real_name: string; student_no: string | null}

export function ClassManagement() {
  const {message} = App.useApp()
  const cache = useQueryClient()
  const [projectFilter, setProjectFilter] = useState<number>()
  const [editor, setEditor] = useState<{id?: number; project_id?: number; name: string; enabled: boolean; teacher_id?: number; teacher_name?: string}>()
  const [projectEditor, setProjectEditor] = useState<{id?: number; abroad_country?: Project['abroad_country']}>()
  const [teacherKeyword, setTeacherKeyword] = useState('')
  const [roster, setRoster] = useState<Classroom>()
  const projects = useQuery({
    queryKey: [...classroomsQuery, 'projects'],
    queryFn: () => api<Project[]>(classroomsEndpoint + '/projects'),
  })
  const classes = useQuery({
    queryKey: [...classroomsQuery, 'classes', projectFilter],
    queryFn: () => api<Classroom[]>(classroomsEndpoint + query({project_id: projectFilter})),
  })
  const teachers = useQuery({
    queryKey: [...classroomsQuery, 'teachers', teacherKeyword],
    enabled: !!editor,
    queryFn: () => api<Teacher[]>(classroomsEndpoint + '/teachers' + query({keyword: teacherKeyword})),
  })
  const students = useQuery({
    queryKey: [...classroomsQuery, 'roster', roster?.id],
    enabled: !!roster,
    queryFn: () => api<Student[]>(classroomsEndpoint + '/' + roster!.id + '/students'),
  })
  const save = useMutation({
    mutationFn: (row: NonNullable<typeof editor>) => row.id
      ? api(classroomsEndpoint + '/' + row.id, {method: 'PUT', body: {name: row.name, teacher_id: row.teacher_id, enabled: row.enabled}})
      : api(classroomsEndpoint, {method: 'POST', body: {project_id: row.project_id, name: row.name, teacher_id: row.teacher_id, enabled: row.enabled}}),
    onSuccess: () => {
      setEditor(undefined)
      void cache.invalidateQueries({queryKey: classroomsQuery})
      void message.success('班级已保存')
    },
  })
  const saveProject = useMutation({
    mutationFn: () => api(classroomsEndpoint + '/projects/' + projectEditor!.id, {
      method: 'PUT', body: {abroad_country: projectEditor!.abroad_country},
    }),
    onSuccess: () => {
      setProjectEditor(undefined)
      void cache.invalidateQueries({queryKey: classroomsQuery})
      void message.success('项目设置已保存')
    },
  })
  const projectOptions = (projects.data ?? []).filter(project => project.abroad_country !== null)
    .map(project => ({value: project.id, label: project.project_name}))
  const projectById = new Map(projects.data?.map(project => [project.id, project]))
  const teacherOptions = (teachers.data ?? []).map(row => ({value: row.id, label: row.real_name}))
  if (editor?.teacher_id && editor.teacher_name && !teacherOptions.some(row => row.value === editor.teacher_id)) {
    teacherOptions.push({value: editor.teacher_id, label: editor.teacher_name})
  }

  return <>
    <PageTitle title="班级管理" description="每个项目可有多个班级，每个班级指定一名班主任。"
      extra={<Space>
        <Button onClick={() => {
          saveProject.reset()
          setProjectEditor({id: projectFilter, abroad_country: projectById.get(projectFilter ?? 0)?.abroad_country})
        }}>项目设置</Button>
        <Button type="primary" disabled={projectOptions.length === 0}
          onClick={() => {
            save.reset(); setTeacherKeyword('')
            setEditor({project_id: projectFilter, name: '', enabled: true})
          }}>新增班级</Button>
      </Space>}/>
    <ErrorNotice error={projects.error || classes.error}/>
    <Card>
      <Select aria-label="按项目筛选" placeholder="全部项目" allowClear showSearch={{optionFilterProp: 'label'}}
        style={{width: 280, marginBottom: 16}} options={projectOptions}
        value={projectFilter} onChange={setProjectFilter}/>
      <Table<Classroom> rowKey="id" loading={classes.isFetching} dataSource={classes.data ?? []}
        locale={{emptyText: projectOptions.length ? '暂无班级' : '请先在项目设置中配置留学地区'}}
        columns={[
          {title: '班级', dataIndex: 'name'},
          {title: '所属项目', render: (_, row) => projectById.get(row.project_id)?.project_name ?? '—'},
          {title: '班主任', dataIndex: 'teacher_name'},
          {title: '学生人数', dataIndex: 'student_count'},
          {title: '招生状态', render: (_, row) => <Tag color={row.enabled ? 'success' : 'default'}>
            {row.enabled ? '可入班' : '停止入班'}
          </Tag>},
          {title: '操作', render: (_, row) => <Space>
            <Button type="link" onClick={() => setRoster(row)}>查看名册</Button>
            <Button type="link" onClick={() => {save.reset(); setTeacherKeyword(''); setEditor(row)}}>编辑</Button>
          </Space>},
        ]}/>
    </Card>
    <StudentPlacement/>
    <Modal title={editor?.id ? '编辑班级' : '新增班级'} open={!!editor}
      onCancel={() => {if (!save.isPending) setEditor(undefined)}} confirmLoading={save.isPending}
      okButtonProps={{disabled: !editor?.project_id || !editor.name.trim() || !editor.teacher_id}}
      onOk={() => {if (editor) save.mutate(editor)}}>
      {editor && <Space orientation="vertical" style={{width: '100%'}}>
        <label htmlFor="class-project">所属项目</label>
        <Select id="class-project" value={editor.project_id} options={projectOptions}
          placeholder="选择项目" style={{width: '100%'}} showSearch={{optionFilterProp: 'label'}}
          disabled={!!editor.id || save.isPending} onChange={project_id => setEditor({...editor, project_id})}/>
        <label htmlFor="class-name">班级名称</label>
        <Input id="class-name" value={editor.name} maxLength={100} disabled={save.isPending}
          onChange={event => setEditor({...editor, name: event.target.value})}/>
        <label htmlFor="class-teacher">班主任</label>
        <Select id="class-teacher" value={editor.teacher_id} options={teacherOptions}
          loading={teachers.isFetching} disabled={save.isPending} style={{width: '100%'}}
          placeholder="选择该班级的班主任" showSearch={{filterOption: false, onSearch: setTeacherKeyword}}
          onChange={teacher_id => setEditor({...editor, teacher_id})}/>
        <ErrorNotice error={teachers.error}/>
        <Space><Switch aria-label="允许新学生入班" checked={editor.enabled} disabled={save.isPending}
          onChange={enabled => setEditor({...editor, enabled})}/>允许新学生入班</Space>
        <ErrorNotice error={save.error}/>
      </Space>}
    </Modal>
    <Modal title="项目设置" open={!!projectEditor}
      onCancel={() => {if (!saveProject.isPending) setProjectEditor(undefined)}}
      confirmLoading={saveProject.isPending}
      okButtonProps={{disabled: !projectEditor?.id || !projectEditor.abroad_country}}
      onOk={() => saveProject.mutate()}>
      {projectEditor && <Space orientation="vertical" style={{width: '100%'}}>
        <label htmlFor="teaching-project">项目</label>
        <Select id="teaching-project" value={projectEditor.id} style={{width: '100%'}}
          disabled={saveProject.isPending} showSearch={{optionFilterProp: 'label'}}
          options={(projects.data ?? []).map(row => ({value: row.id, label: row.project_name}))}
          onChange={id => setProjectEditor({id, abroad_country: projectById.get(id)?.abroad_country})}/>
        <label htmlFor="teaching-country">留学地区</label>
        <Select id="teaching-country" value={projectEditor.abroad_country} style={{width: '100%'}}
          disabled={saveProject.isPending}
          options={[{value: 'Germany', label: '德国'}, {value: 'Singapore', label: '新加坡'}]}
          onChange={abroad_country => setProjectEditor({...projectEditor, abroad_country})}/>
        <ErrorNotice error={saveProject.error}/>
      </Space>}
    </Modal>
    <Modal title={roster ? roster.name + ' · 学生名册' : '学生名册'} open={!!roster}
      onCancel={() => setRoster(undefined)} footer={null}>
      <ErrorNotice error={students.error}/>
      <Table<Student> rowKey="id" dataSource={students.data ?? []} loading={students.isFetching}
        columns={[{title: '学生', dataIndex: 'real_name'}, {title: '档案编号', dataIndex: 'id'},
          {title: '学号', render: (_, student) => student.student_no ?? '—'}]}/>
    </Modal>
  </>
}
