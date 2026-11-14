import {Alert, Button, Card, Empty, Input, Space, Spin, Table, Tag, Typography} from 'antd'
import {useQuery} from '@tanstack/react-query'
import {useState} from 'react'
import {useAuth} from '../auth'
import {api, query} from '../lib/api'
import {ActionModal, ErrorNotice, PageTitle, type ActionSpec, type Field} from '../components/shared'

type Request = <T>(path: string) => Promise<T>
type Course = {
  id: number; project_name: string; category: string | null; description: string | null
  target_audience: string | null; duration: string | null; price: string | null
}
type CoursePage = {items: Course[]; next_after_id: number | null}

export function WebsiteCourses({request}: {request: Request}) {
  const [keyword, setKeyword] = useState('')
  const [after, setAfter] = useState(0)
  const result = useQuery({
    queryKey: ['visitor', 'courses', keyword, after],
    queryFn: () => request<CoursePage>('/api/v1/visitors/courses?' + new URLSearchParams({
      keyword, after_id: String(after), limit: '12',
    })),
  })
  return <Space orientation="vertical" style={{width: '100%'}} size="middle">
    <Input.Search aria-label="查询课程和项目" placeholder="按课程名称或类别查询" maxLength={64}
      allowClear onSearch={value => {setAfter(0); setKeyword(value.trim())}}/>
    {result.error && <Alert showIcon type="error" title={result.error.message}/>}
    {result.isFetching && <Spin/>}
    {!result.isFetching && !result.error && !result.data?.items.length && <Empty description="暂无符合条件的上架课程"/>}
    <div className="visitor-programs">
      {result.data?.items.map(course => <Card key={course.id} title={course.project_name}>
        {course.category && <Tag>{course.category}</Tag>}
        {course.description && <Typography.Paragraph style={{whiteSpace: 'pre-wrap'}}>{course.description}</Typography.Paragraph>}
        {course.target_audience && <Typography.Paragraph>适合人群：{course.target_audience}</Typography.Paragraph>}
        {course.duration && <Typography.Paragraph>课程周期：{course.duration}</Typography.Paragraph>}
        {course.price !== null && <Typography.Text>价格：¥{course.price}</Typography.Text>}
      </Card>)}
    </div>
    <Space>
      <Button disabled={!after || result.isFetching} onClick={() => setAfter(0)}>返回首批</Button>
      <Button disabled={!result.data?.next_after_id || result.isFetching}
        onClick={() => setAfter(result.data?.next_after_id ?? after)}>查看更多</Button>
    </Space>
  </Space>
}


type StaffCourse = Course & {status: 0 | 1}
const staffEndpoint = '/api/v1/enterprise/courses'
const courseFields: Field[] = [
  {name: 'project_name', label: '课程或项目名称', required: true},
  {name: 'category', label: '类别'}, {name: 'target_audience', label: '适合人群'},
  {name: 'duration', label: '周期'}, {name: 'price', label: '价格（元）', kind: 'number', precision: 2},
  {name: 'description', label: '详情', kind: 'textarea'},
  {name: 'status', label: '发布状态', kind: 'select', required: true, initial: 0,
    options: [{value: 0, label: '下架'}, {value: 1, label: '上架'}]},
]

export function StaffCourses() {
  const {user} = useAuth()
  const [keyword, search] = useState('')
  const [after, setAfter] = useState(0)
  const [action, setAction] = useState<ActionSpec | null>(null)
  const records = useQuery({
    queryKey: [user?.id, 'staff-courses', keyword, after],
    queryFn: () => api<{items: StaffCourse[]; next_after_id: number | null}>(staffEndpoint + query({keyword, after_id: after})),
  })
  function edit(row?: StaffCourse) {
    setAction({
      title: row ? '编辑课程' : '新增课程',
      path: row ? staffEndpoint + '/' + row.id : staffEndpoint,
      method: row ? 'PUT' : 'POST', fields: courseFields,
      initial: row ? {...row, price: row.price === null ? null : Number(row.price)} : undefined,
    })
  }
  return <>
    <PageTitle title="课程管理" description="维护官网登录后可查询的课程和项目。"
      extra={<Button type="primary" onClick={() => edit()}>新增课程</Button>}/>
    <ErrorNotice error={records.error}/>
    <Card>
      <Input.Search aria-label="搜索课程" placeholder="按课程名称或类别查询" maxLength={64} allowClear
        onSearch={value => {search(value.trim()); setAfter(0)}}/>
      <Table<StaffCourse> rowKey="id" loading={records.isFetching} dataSource={records.data?.items || []}
        pagination={false} scroll={{x: 620}} style={{marginTop: 16}} columns={[
          {title: '课程或项目', dataIndex: 'project_name'}, {title: '类别', dataIndex: 'category'},
          {title: '周期', dataIndex: 'duration'}, {title: '价格（元）', dataIndex: 'price'},
          {title: '状态', render: (_, row) => <Tag>{row.status === 1 ? '已上架' : '下架'}</Tag>},
          {title: '操作', render: (_, row) => <Button type="link" onClick={() => edit(row)}>编辑</Button>},
        ]}/>
      <Space style={{marginTop: 12}}>
        <Button disabled={!after || records.isFetching} onClick={() => setAfter(0)}>返回首批</Button>
        <Button disabled={!records.data?.next_after_id || records.isFetching}
          onClick={() => setAfter(records.data?.next_after_id ?? after)}>查看更多</Button>
      </Space>
    </Card>
    <ActionModal action={action} onClose={() => setAction(null)}/>
  </>
}
