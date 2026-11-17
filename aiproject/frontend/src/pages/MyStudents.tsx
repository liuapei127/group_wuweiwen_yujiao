import {useState} from 'react'
import {App, Button, Card, Descriptions, Drawer, Input, Select, Space, Table, Tabs, Tag} from 'antd'
import {useQuery} from '@tanstack/react-query'
import {Link} from 'react-router-dom'
import {useAuth} from '../auth'
import {ErrorNotice, PageTitle, Status} from '../components/shared'
import {api, download, query, type Row} from '../lib/api'

type Class = {id: number; name: string; project_name: string; student_count: number; enabled: boolean}
type Student = {
  id: number; real_name: string; student_no: string | null; class_id: number | null
  class_name: string | null; project_name: string | null; school: string | null
  major: string | null; abroad_country: string | null; contact_info: string | null; status: string
}
type StudentPage = {items: Student[]; has_more: boolean}
const root = '/api/v1/teacher'
const countries: Record<string, string> = {Germany: '德国', Singapore: '新加坡'}

export function MyStudents() {
  const {user} = useAuth()
  const [classId, setClassId] = useState<number>()
  const [keyword, setKeyword] = useState('')
  const [offset, setOffset] = useState(0)
  const [selected, select] = useState<Student>()
  const classes = useQuery({
    queryKey: [user?.id, 'my-classes'], queryFn: () => api<Class[]>(root + '/classes'),
  })
  const students = useQuery({
    queryKey: [user?.id, 'my-students', classId, keyword, offset],
    queryFn: () => api<StudentPage>(root + '/students' + query({class_id: classId, keyword, offset})),
  })
  return <>
    <PageTitle title="我的班级与学生" description="查看本人负责的班级、学生档案和学务记录。"/>
    <ErrorNotice error={classes.error || students.error}/>
    <Card>
      <Space wrap style={{marginBottom: 16}}>
        <Select aria-label="我的班级" value={classId} allowClear placeholder="全部学生（含待入班）"
          style={{minWidth: 300}} loading={classes.isFetching}
          options={(classes.data ?? []).map(row => ({
            value: row.id, label: row.project_name + ' · ' + row.name + '（' + row.student_count + '人）',
          }))}
          onChange={value => {setClassId(value); setOffset(0)}}/>
        <Input.Search aria-label="搜索学生" placeholder="姓名或学号" allowClear
          onSearch={value => {setKeyword(value.trim()); setOffset(0)}}/>
      </Space>
      <Table<Student> rowKey="id" dataSource={students.data?.items ?? []} loading={students.isFetching}
        pagination={false} scroll={{x: 850}} columns={[
          {title: '学生', dataIndex: 'real_name'},
          {title: '学号', render: (_, row) => row.student_no ?? '—'},
          {title: '项目', render: (_, row) => row.project_name ?? '待确认'},
          {title: '班级', render: (_, row) => row.class_name ?? <Tag>待入班</Tag>},
          {title: '留学地区', render: (_, row) => countries[row.abroad_country ?? ''] ?? row.abroad_country ?? '待确认'},
          {title: '操作', render: (_, row) => <Button type="link" onClick={() => select(row)}>学生详情</Button>},
        ]}/>
      <Space style={{marginTop: 12}}>
        <Button disabled={!offset || students.isFetching} onClick={() => setOffset(value => value - 20)}>上一页</Button>
        <Button disabled={!students.data?.has_more || students.isFetching} onClick={() => setOffset(value => value + 20)}>下一页</Button>
      </Space>
    </Card>
    {selected && <StudentDetails key={selected.id} student={selected} close={() => select(undefined)}/>}
  </>
}

function StudentDetails({student, close}: {student: Student; close: () => void}) {
  const {message} = App.useApp()
  const {user, can} = useAuth()
  const [kind, setKind] = useState('leaves')
  const [before, setBefore] = useState<number>()
  const permission = kind === 'leaves' ? 'leaves:read' : 'tickets:read'
  const records = useQuery({
    queryKey: [user?.id, 'student-history', student.id, kind, before], enabled: can(permission),
    queryFn: () => api<{items: Row[]; has_more: boolean}>(root + '/students/' + student.id + '/records/' + kind + query({before_id: before})),
  })
  const detail = useQuery({
    queryKey: [user?.id, 'student-detail', student.id],
    queryFn: () => api<Student>(root + '/students/' + student.id),
  })
  const row = detail.data ?? student
  const destinations = [
    ['scores:read', '/scores', '成绩'],
    ['academics:read', '/academic-deadlines', '考务'],
    ['applications:read', '/application-progress', '申请进度'],
    ['student-alerts:read', '/student-alerts', '心理预警'],
  ]
  return <Drawer title={row.real_name + ' · 学生详情'} open onClose={close} size={760}>
    <ErrorNotice error={detail.error}/>
    <Descriptions column={2} items={[
      {key: 'number', label: '学号', children: row.student_no ?? '—'},
      {key: 'contact', label: '联系方式', children: row.contact_info ?? '—'},
      {key: 'project', label: '项目', children: row.project_name ?? '待确认'},
      {key: 'class', label: '班级', children: row.class_name ?? '待入班'},
      {key: 'school', label: '院校', children: row.school ?? '—'},
      {key: 'major', label: '专业', children: row.major ?? '—'},
      {key: 'region', label: '留学地区', children: countries[row.abroad_country ?? ''] ?? row.abroad_country ?? '—'},
    ]}/>
    <Space wrap style={{margin: '16px 0'}}>
      {destinations.filter(([permission]) => can(permission)).map(([, path, label]) =>
        <Link key={path} to={path + query({student_id: row.id})}><Button>{label}</Button></Link>)}
    </Space>
    <Tabs activeKey={kind} onChange={value => {setKind(value); setBefore(undefined)}}
      items={[{key: 'leaves', label: '请假记录'}, {key: 'complaints', label: '学习反馈'}]}/>
    <ErrorNotice error={records.error}/>
    {can(permission) && <>
      <Table<Row> rowKey="id" loading={records.isFetching} dataSource={records.data?.items ?? []} pagination={false}
        columns={kind === 'leaves' ? [
          {title: '开始', dataIndex: 'start_time'}, {title: '结束', dataIndex: 'end_time'},
          {title: '原因', dataIndex: 'reason'}, {title: '状态', render: (_, item) => <Status value={item.status}/>},
          {title: '审批意见', dataIndex: 'approval_comment'},
          {title: '证明', render: (_, item) => item.attachment_url && <Button type="link"
            onClick={() => void download('/api/v1/student-admin/leaves/' + item.id + '/attachment', '请假证明')
              .catch((error: Error) => void message.error(error.message))}>查看附件</Button>},
        ] : [
          {title: '标题', dataIndex: 'title'}, {title: '内容', dataIndex: 'content'},
          {title: '状态', render: (_, item) => <Status value={item.status}/>},
          {title: '处理结果', dataIndex: 'solution'},
        ]}/>
      <Space style={{marginTop: 12}}>
        <Button disabled={!before || records.isFetching} onClick={() => setBefore(undefined)}>返回最新</Button>
        <Button disabled={!records.data?.has_more || records.isFetching}
          onClick={() => setBefore(records.data?.items.at(-1)?.id)}>查看更多</Button>
      </Space>
    </>}
  </Drawer>
}
