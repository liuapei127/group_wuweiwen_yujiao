import {Alert, Button, Empty, Tag} from 'antd'
import {useQuery} from '@tanstack/react-query'
import {ArrowRightOutlined, CalendarOutlined, CommentOutlined, GlobalOutlined, LineChartOutlined} from '@ant-design/icons'
type Request = <T>(path: string, method?: string, body?: unknown) => Promise<T>
type Home = {profile: {student_name?: string; abroad_country?: string}; applications: {id: number; school: string; stage_label: string; next_action?: string; updated_at: string}[]; deadlines: {id: number; title: string; deadline: string}[]}
export function StudentHome({request, open, chat}: {request: Request; open: (key: string) => void; chat: (query?: string) => void}) {
  const info = useQuery({queryKey: ['visitor', 'student', 'home'], queryFn: () => request<Home>('/api/v1/student/assistant/overview'), refetchOnWindowFocus: true})
  const notices = useQuery({queryKey: ['visitor', 'student', 'home-notices'], queryFn: () => request<{id: number; title: string; content: string; related_summary?: string}[]>('/api/v1/student/notifications?limit=3'), refetchOnWindowFocus: true})
  const profile = info.data?.profile
  const country = profile?.abroad_country === 'Singapore' ? '新加坡' : profile?.abroad_country === 'Germany' ? '德国' : '你的下一站'
  return <div className="stu-home">
    <section className="stu-home__hero"><div className="stu-home__hero-copy"><span className="stu-overline">YOUR STUDENT SPACE · 学生服务中心</span><h1>欢迎回来{profile?.student_name ? '，' + profile.student_name : ''}。</h1><p>新的生活，慢慢适应。<br/>想聊聊、找答案，或把眼前的事情安排好，我们一起。</p><Button size="large" type="primary" onClick={() => chat()}>和学生助手聊聊 <ArrowRightOutlined/></Button><small>留学方向 · {country}</small></div><div aria-label={country + '生活场景示意'} role="img" className={'stu-home__visual ' + (country === '新加坡' ? 'is-singapore' : 'is-germany')}><div><span>每一步，都可以更从容</span><small>场景示意</small></div></div></section>
    {info.error && <Alert showIcon type="warning" title="暂时没有读到你的最新资料" description={(info.error as Error).message} action={<Button onClick={() => void info.refetch()}>重新读取</Button>}/>}
    <section className="stu-home__quick" aria-label="常用服务">{[
      {title: '申请请假', detail: '选好时间，一步步准备', icon: <CalendarOutlined/>, action: () => chat('我要请假')},
      {title: '查看申请', detail: '院校进展与下一步', icon: <LineChartOutlined/>, action: () => open('progress')},
      {title: '生活指南', detail: '出行、住宿与常用帮助', icon: <GlobalOutlined/>, action: () => open('overseas')},
      {title: '聊聊近况', detail: '遇到烦恼，也可以说说', icon: <CommentOutlined/>, action: () => chat('我想聊聊最近的生活')},
    ].map(item => <button key={item.title} onClick={item.action}><span>{item.icon}</span><div><strong>{item.title}</strong><small>{item.detail}</small></div><ArrowRightOutlined/></button>)}</section>
    <div className="stu-home__updates"><section><div className="stu-section-title"><h2>接下来要留意的事</h2><Button type="link" onClick={() => open('deadlines')}>全部考务 →</Button></div>{info.isFetching && !info.data ? <p>正在读取…</p> : !info.data?.deadlines?.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="近期没有登记的考务待办"/> : info.data.deadlines.map(row => <button className="stu-home__row" key={row.id} onClick={() => open('deadlines')}><div><strong>{row.title}</strong><small>截止：{row.deadline.slice(0, 16).replace('T', ' ')}（北京时间）</small></div><ArrowRightOutlined/></button>)}</section>
      <section><div className="stu-section-title"><h2>我的院校申请</h2><Button type="link" onClick={() => open('progress')}>查看详情 →</Button></div>{!info.data?.applications?.length ? <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂未登记院校申请进度"/> : info.data.applications.slice(0, 3).map(row => <button className="stu-home__row" key={row.id} onClick={() => open('progress')}><div><strong>{row.school} <Tag>{row.stage_label}</Tag></strong><small>下一步：{row.next_action || '请向负责人确认'}</small><small>记录更新：{row.updated_at.slice(0, 16).replace('T', ' ')}（北京时间）</small></div><ArrowRightOutlined/></button>)}</section></div>
    <section className="stu-home__notifications"><div className="stu-section-title"><h2>近期通知</h2><Button type="link" onClick={() => open('notifications')}>查看全部 →</Button></div>{notices.error ? <p>通知暂时无法读取，请稍后重试。</p> : !notices.data?.length ? <p>有新的处理结果时，可以在这里查看。</p> : notices.data.map(row => <button className="stu-home__row" key={row.id} onClick={() => open('notifications')}><div><strong>{row.title}</strong><small>{row.related_summary || row.content}</small></div><ArrowRightOutlined/></button>)}</section>
  </div>
}
