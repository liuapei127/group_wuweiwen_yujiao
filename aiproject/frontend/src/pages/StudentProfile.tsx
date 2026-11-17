import {Alert, Button, Card, Descriptions, Space} from 'antd'
import {useQuery} from '@tanstack/react-query'
import {ErrorNotice, PageTitle} from '../components/shared'

type Request = <T>(path: string, method?: string, body?: unknown) => Promise<T>
type AcademicProfile = {
  student_name: string; student_no: string | null; school: string | null; major: string | null
  abroad_country: string | null; class_teacher: string | null
  class_id: number | null; class_name: string | null; project_id: number | null; project_name: string | null
}

export function StudentProfile({request, token, back}: {request: Request; token: string; back: () => void}) {
  const profile = useQuery({
    queryKey: ['visitor', 'student', 'academic-profile', token],
    queryFn: () => request<AcademicProfile>('/api/v1/student/academic-profile'),
    refetchOnWindowFocus: true,
  })
  const row = profile.data
  const country = row?.abroad_country?.trim()
  const destination = country === 'Germany' ? '德国' : country === 'Singapore' ? '新加坡' : country
  return <section className="visitor-section customer-website-profile">
    <PageTitle title="我的学籍资料" description="查看老师登记的学生档案；账号昵称、联系方式和头像可在「个人信息」中编辑。"
      extra={<Button onClick={back}>返回学生服务</Button>}/>
    <ErrorNotice error={profile.error}/>
    <Space orientation="vertical" size="middle" style={{width: '100%'}}>
      <Card title="学生学籍" loading={profile.isPending}>
        {row && <Descriptions column={1} items={[
          {key: 'name', label: '学籍姓名', children: row.student_name},
          {key: 'number', label: '学号', children: row.student_no || '老师尚未登记'},
          {key: 'project', label: '所属项目', children: row.project_name || '尚未分配'},
          {key: 'class', label: '当前班级', children: row.class_name || '尚未分班'},
          {key: 'country', label: '留学地区', children: destination || '老师尚未登记'},
          {key: 'school', label: '当前就读院校', children: row.school || '老师尚未登记'},
          {key: 'major', label: '当前专业', children: row.major || '老师尚未登记'},
          {key: 'teacher', label: '班主任', children: row.class_teacher || '尚未分配有效班主任'},
        ]}/>}
      </Card>
      <Alert type="info" showIcon title="学籍信息有误时，请联系班主任核对更正。"
        description="申请中的目标院校请到「申请进度」查看；上传材料和预约记录在「我的材料与活动」。"/>
    </Space>
  </section>
}
