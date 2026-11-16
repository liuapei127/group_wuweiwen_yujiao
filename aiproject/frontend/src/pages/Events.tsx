import {useState} from 'react'
import {App, Button, Card, Form, Input, InputNumber, Modal, Popconfirm, Space, Switch, Table, Tag} from 'antd'
import {useQuery, useQueryClient} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ErrorNotice, PageTitle} from '../components/shared'
import {api, query} from '../lib/api'

type EventFields = {
  event_name: string; description?: string; location: string; start_time: string
  end_time: string; max_participants: number; is_published?: boolean
}
type Activity = Omit<EventFields, 'description' | 'location' | 'end_time' | 'max_participants' | 'is_published'> & {
  id: number; description: string | null; location: string | null; end_time: string | null
  current_participants: number; max_participants: number | null; is_published: boolean
}
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
  const [eventForm, setEventForm] = useState<{event?: Activity}>()
  const [saving, setSaving] = useState(false)
  const [changing, setChanging] = useState<number>()
  const [selected, select] = useState<Activity>()
  const [eventBefore, setEventBefore] = useState<number>()
  const [registrationAfter, setRegistrationAfter] = useState(0)
  const [checkingIn, setCheckingIn] = useState<number>()
  const canManage = can('events:manage')
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

  function openEventForm(event?: Activity) {
    form.resetFields()
    form.setFieldsValue(event ? {
      event_name: event.event_name,
      description: event.description ?? undefined,
      location: event.location ?? undefined,
      start_time: event.start_time,
      end_time: event.end_time ?? undefined,
      max_participants: event.max_participants ?? undefined,
    } : {is_published: true})
    setEventForm({event})
  }

  async function refreshEvents() {
    await Promise.all([
      cache.invalidateQueries({queryKey: [user?.id, 'staff-events']}),
      cache.invalidateQueries({queryKey: ['visitor', 'activities']}),
      cache.invalidateQueries({queryKey: ['visitor', 'bookings']}),
    ])
  }

  async function saveEvent(values: EventFields) {
    const event = eventForm?.event
    setSaving(true)
    try {
      const {is_published, ...details} = values
      await api(event ? endpoint + '/' + event.id : endpoint, {
        method: event ? 'PUT' : 'POST',
        body: event ? details : {...details, is_published},
      })
      setEventForm(undefined)
      if (!event) setEventBefore(undefined)
      await refreshEvents()
      void message.success(event ? '活动已更新' : is_published ? '活动已发布' : '未发布活动已保存')
    } catch (error) {
      void message.error((error as Error).message)
    } finally {
      setSaving(false)
    }
  }

  async function changeEvent(event: Activity, action: 'publication' | 'delete') {
    setChanging(event.id)
    try {
      const url = endpoint + '/' + event.id
      if (action === 'publication') {
        await api(url + '/publication', {method: 'PATCH', body: {is_published: !event.is_published}})
        void message.success(event.is_published ? '活动已下架' : '活动已发布')
      } else {
        await api(url, {method: 'DELETE'})
        if (activities.data?.length === 1) setEventBefore(undefined)
        void message.success('活动已删除')
      }
      await refreshEvents()
    } catch (error) {
      void message.error((error as Error).message)
    } finally {
      setChanging(undefined)
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
    <PageTitle title="活动管理" description="管理活动和发布状态，查看预约名单并为到场游客签到。"/>
    {canManage && <Button type="primary" onClick={() => openEventForm()}>创建活动</Button>}
    <ErrorNotice error={activities.error}/>
    <Card style={{marginTop: 16}}>
      <Table rowKey="id" dataSource={activities.data || []} loading={activities.isLoading}
        pagination={false} scroll={{x: canManage ? 990 : 760}} columns={[
          {title: '活动', dataIndex: 'event_name'},
          {title: '开始时间（北京时间）', dataIndex: 'start_time', render: value => value.replace('T', ' ')},
          {title: '地点', dataIndex: 'location'},
          {title: '已用名额', render: (_, row) => row.current_participants + ' / ' + (row.max_participants ?? '未设置')},
          {title: '发布状态', render: (_, row) => row.is_published
            ? <Tag color="success">已发布</Tag> : <Tag>未发布</Tag>},
          {title: '操作', render: (_, row) => <Space size={0} wrap>
            {canCheckIn && <Button type="link" onClick={() => {
              select(row)
              setRegistrationAfter(0)
            }}>预约名单</Button>}
            {canManage && <>
              <Button type="link" disabled={changing !== undefined}
                onClick={() => openEventForm(row)}>编辑</Button>
              <Button type="link" disabled={changing !== undefined}
                onClick={() => void changeEvent(row, 'publication')}>{row.is_published ? '下架' : '发布'}</Button>
              <Popconfirm title="删除这场活动？" description={row.event_name}
                okText="删除" cancelText="取消" okButtonProps={{danger: true}}
                onConfirm={() => changeEvent(row, 'delete')}>
                <Button type="link" danger disabled={changing !== undefined}>删除</Button>
              </Popconfirm>
            </>}
          </Space>},
        ]}/>
      <Space style={{marginTop: 12}}>
        <Button disabled={eventBefore === undefined} onClick={() => setEventBefore(undefined)}>返回最新</Button>
        <Button disabled={activities.data?.length !== 50} onClick={() => setEventBefore(activities.data?.at(-1)?.id)}>查看更多</Button>
      </Space>
    </Card>
    <Modal title={eventForm?.event ? '编辑活动' : '创建活动'} open={!!eventForm}
      onCancel={() => setEventForm(undefined)} closable={!saving} keyboard={!saving}
      mask={{closable: !saving}} footer={null} forceRender>
      <Form form={form} layout="vertical" disabled={saving} onFinish={value => void saveEvent(value)}>
        <Form.Item name="event_name" label="活动名称" rules={[{required: true, whitespace: true}]}><Input maxLength={255}/></Form.Item>
        <Form.Item name="location" label="地点" rules={[{required: true, whitespace: true}]}><Input maxLength={255}/></Form.Item>
        <Form.Item name="start_time" label="开始时间（北京时间）" rules={[{required: true}]}><Input type="datetime-local" step={1}/></Form.Item>
        <Form.Item name="end_time" label="结束时间（北京时间）" rules={[{required: true}]}><Input type="datetime-local" step={1}/></Form.Item>
        <Form.Item name="max_participants" label="名额上限" rules={[{required: true}]}>
          <InputNumber min={1} max={2147483647} precision={0}/>
        </Form.Item>
        <Form.Item name="description" label="活动说明"><Input.TextArea maxLength={10000}/></Form.Item>
        {!eventForm?.event && <Form.Item name="is_published" label="保存后发布" valuePropName="checked">
          <Switch/>
        </Form.Item>}
        <Button type="primary" htmlType="submit" loading={saving}>保存活动</Button>
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
