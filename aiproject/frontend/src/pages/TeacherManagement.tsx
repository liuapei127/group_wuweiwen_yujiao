import {useState} from 'react'
import {Button, Card, Input, Space, Table} from 'antd'
import {useQuery} from '@tanstack/react-query'
import {Link} from 'react-router-dom'
import {useAuth} from '../auth'
import {ErrorNotice, PageTitle} from '../components/shared'
import {api, query} from '../lib/api'
import {classroomsEndpoint, classroomsQuery, type Classroom, type Project, type Teacher} from './ClassManagement'

export function TeacherManagement() {
  const {can} = useAuth()
  const [keyword, setKeyword] = useState('')
  const projects = useQuery({
    queryKey: [...classroomsQuery, 'projects'],
    queryFn: () => api<Project[]>(classroomsEndpoint + '/projects'),
  })
  const teachers = useQuery({
    queryKey: [...classroomsQuery, 'teachers', keyword],
    queryFn: () => api<Teacher[]>(classroomsEndpoint + '/teachers' + query({keyword})),
  })
  const classes = useQuery({
    queryKey: [...classroomsQuery, 'classes'],
    queryFn: () => api<Classroom[]>(classroomsEndpoint),
  })
  const projectById = new Map(projects.data?.map(project => [project.id, project]))

  return <>
    <PageTitle title="老师管理" description="查看班主任负责的班级和学生人数，在班级管理中安排或调整班主任。"
      extra={<Space>
        <Link to="/class-management"><Button type="primary">分配班级班主任</Button></Link>
        {can('users:manage') && <Link to="/settings/users"><Button>管理员工账号</Button></Link>}
      </Space>}/>
    <ErrorNotice error={projects.error || classes.error || teachers.error}/>
    <Card title="班主任与负责班级">
      <Input.Search aria-label="搜索老师" placeholder="按姓名搜索老师" allowClear
        style={{width: 300, marginBottom: 12}} onSearch={value => setKeyword(value.trim())}/>
      <Table<Teacher> rowKey="id" loading={teachers.isFetching || classes.isFetching} dataSource={teachers.data ?? []}
        columns={[
          {title: '姓名', dataIndex: 'real_name'},
          {title: '员工编号', dataIndex: 'id'},
          {title: '负责班级', render: (_, row) => (classes.data ?? [])
            .filter(classroom => classroom.teacher_id === row.id)
            .map(classroom => (projectById.get(classroom.project_id)?.project_name ?? '') + ' · ' + classroom.name)
            .join('、') || '待分配'},
          {title: '学生人数', render: (_, row) => (classes.data ?? [])
            .filter(classroom => classroom.teacher_id === row.id)
            .reduce((total, classroom) => total + classroom.student_count, 0)},
        ]}/>
    </Card>
  </>
}
