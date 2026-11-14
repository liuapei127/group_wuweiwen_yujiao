import {useState} from 'react'
import {App, Button, Card, Form, Input, InputNumber, Modal, Space, Table, Tag} from 'antd'
import {useQuery, useQueryClient} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ErrorNotice, PageTitle} from '../components/shared'
import {api, query} from '../lib/api'

type EventFields = {
  event_name: string; description?: string; location: string; start_time: string
  end_time: string; max_participants: number
}
type Activity = Omit<EventFields, "max_participants"> & {id: number; current_participants: number; max_participants: number | null}
type Registration = {
  id: number; customer_id: number | null; customer_name: string | null
  status: string; attended_at: string | null; checked_in_by: number | null
}
const endpoint = '/api/v1/enterprise/events'
const statusNames: Record<string, string> = {registered: '已预约', cancelled: '已取消', attended: '已签到'}

export function Events() {
  const {can, user} = useAuth()
  const {message} = App.useApp()
  const cache = useQueryClient()
  const [form] = Form.useForm<EventFields>()
  const [createOpen, setCreateOpen] = useState(false)
  const [creating, setCreating] = useState(false)
  const [selected, select] = useState<Activity>()
  const [eventBefore, setEventBefore] = useState<number>()
  const [registrationAfter, setRegistrationAfter] = useState(0)
  const [checkingIn, setCheckingIn] = useState<number>()
  const canCheckIn = can('events:check_in')
  const activities = useQuery({
    queryKey: [user?.id, 'staff-events', eventBefore],
    queryFn: () => api<Activity[]>(endpoint + query({before_id: eventBefore})),
  })
  const registrations = useQuery({
    queryKey: [user?.id, 'staff-registrations', selected?.id, registrationAfter],
    queryFn: () => api<Registration[]>(endpoint + '/' + selected?.id + '/registrations' + query({after_id: registrationAfter})),
    enabled: !!selected && canCheckIn,
  })

  async function createEvent(values: EventFields) {
    setCreating(true)
    try {
      await api(endpoint, {method: 'POST', body: values})
      form.resetFields()
      setCreateOpen(false)
      setEventBefore(undefined)
      await cache.invalidateQueries({queryKey: [user?.id, 'staff-events']})
      void message.success('活动已创建')
    } catch (error) {
      void message.error((error as Error).message)
    } finally {
      setCreating(false)
    }
  }

  async function checkIn(row: Registration) {
    if (!selected) return
    setCheckingIn(row.id)
    try {
      await api(endpoint + '/' + selected.id + '/registrations/' + row.id + '/check-in', {method: 'POST'})
      void message.success('签到成功')
    } catch (error) {
      void message.error((error as Error).message)
    } finally {
      await cache.invalidateQueries({queryKey: [user?.id, 'staff-registrations', selected.id]})
      setCheckingIn(undefined)
    }
  }

  return <>
    <PageTitle title="活动管理" description="创建活动、查看预约名单，并为到场游客手动签到。"/>
    {can('events:manage') && <Button type="primary" onClick={() => setCreateOpen(true)}>创建活动</Button>}
    <ErrorNotice error={activities.error}/>
    <Card style={{marginTop: 16}}>
      <Table rowKey="id" dataSource={activities.data || []} loading={activities.isLoading}
        pagination={false} scroll={{x: 690}} columns={[
          {title: '活动', dataIndex: 'event_name'},
          {title: '开始时间（北京时间）', dataIndex: 'start_time', render: value => value.replace('T', ' ')},
          {title: '地点', dataIndex: 'location'},
          {title: '已用名额', render: (_, row) => row.current_participants + ' / ' + (row.max_participants ?? '未设置')},
          {title: '操作', render: (_, row) => canCheckIn && <Button type="link" onClick={() => {
            select(row)
            setRegistrationAfter(0)
          }}>预约名单</Button>},
        ]}/>
      <Space style={{marginTop: 12}}>
        <Button disabled={eventBefore === undefined} onClick={() => setEventBefore(undefined)}>返回最新</Button>
        <Button disabled={activities.data?.length !== 50} onClick={() => setEventBefore(activities.data?.at(-1)?.id)}>查看更多</Button>
      </Space>
    </Card>
    <Modal title="创建活动" open={createOpen} onCancel={() => setCreateOpen(false)} footer={null}>
      <Form form={form} layout="vertical" onFinish={value => void createEvent(value)}>
        <Form.Item name="event_name" label="活动名称" rules={[{required: true, whitespace: true}]}><Input maxLength={255}/></Form.Item>
        <Form.Item name="location" label="地点" rules={[{required: true, whitespace: true}]}><Input maxLength={255}/></Form.Item>
        <Form.Item name="start_time" label="开始时间（北京时间）" rules={[{required: true}]}><Input type="datetime-local"/></Form.Item>
        <Form.Item name="end_time" label="结束时间（北京时间）" rules={[{required: true}]}><Input type="datetime-local"/></Form.Item>
        <Form.Item name="max_participants" label="名额上限" rules={[{required: true}]}>
          <InputNumber min={1} max={2147483647} precision={0}/>
        </Form.Item>
        <Form.Item name="description" label="活动说明"><Input.TextArea maxLength={10000}/></Form.Item>
        <Button type="primary" htmlType="submit" loading={creating}>保存活动</Button>
      </Form>
    </Modal>
    <Modal title={selected ? selected.event_name + ' · 预约名单' : '预约名单'} open={!!selected}
      onCancel={() => select(undefined)} footer={null} width={800}>
      <ErrorNotice error={registrations.error}/>
      <Table rowKey="id" dataSource={registrations.data || []} loading={registrations.isLoading}
        pagination={false} scroll={{x: 680}} columns={[
          {title: '游客', render: (_, row) => row.customer_name || (row.customer_id ? '游客 ' + row.customer_id : '历史预约')},
          {title: '预约编号', dataIndex: 'id'},
          {title: '状态', dataIndex: 'status', render: value => <Tag>{statusNames[value]}</Tag>},
          {title: '签到时间', dataIndex: 'attended_at', render: value => value?.replace('T', ' ') || '—'},
          {title: '签到人编号', dataIndex: 'checked_in_by', render: value => value ?? '—'},
          {title: '操作', render: (_, row) => row.status === 'registered' && <Button type="link"
            disabled={checkingIn !== undefined} loading={checkingIn === row.id}
            onClick={() => void checkIn(row)}>签到</Button>},
        ]}/>
      <Space style={{marginTop: 12}}>
        <Button disabled={!registrationAfter} onClick={() => setRegistrationAfter(0)}>返回首批</Button>
        <Button disabled={registrations.data?.length !== 50}
          onClick={() => setRegistrationAfter(registrations.data?.at(-1)?.id ?? registrationAfter)}>查看更多</Button>
      </Space>
    </Modal>
  </>
}
