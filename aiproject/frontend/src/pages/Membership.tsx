import {useState} from 'react'
import {Button, Form, Input, Modal, Select, Space, Switch, Table} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {ErrorNotice} from '../components/shared'
import {api} from '../lib/api'

type Membership = {id: number; org_id: number; org_name: string; status: string; primary: boolean;
  effective_from: string; effective_to: string | null}
type Fields = {org_id: number; status: string; primary: boolean; effective_from: string; effective_to?: string}
const endpoint = '/api/v1/enterprise/organizations'

export function MembershipEditor({userId, close}: {userId: number; close: () => void}) {
  const [form] = Form.useForm<Fields>()
  const [editing, setEditing] = useState(false)
  const cache = useQueryClient()
  const path = endpoint + '/memberships/' + userId
  const rows = useQuery({queryKey: [path], queryFn: () => api<Membership[]>(path)})
  const organizations = useQuery({
    queryKey: [endpoint, 'membership-options'],
    queryFn: () => api<{id: number; org_name: string; manager_id: number | null}[]>(endpoint + '/membership-options'),
  })
  const save = useMutation({
    mutationFn: ({org_id, effective_to, ...values}: Fields) =>
      api(path + '/' + org_id, {method: 'PUT', body: {...values, effective_to: effective_to || null}}),
    onSuccess: () => {setEditing(false); void cache.invalidateQueries({queryKey: [path]})},
  })

  function edit(row?: Membership) {
    form.resetFields()
    save.reset()
    form.setFieldsValue({
      org_id: row?.org_id,
      status: row?.status || 'active',
      primary: row?.primary || false,
      effective_from: (row?.effective_from || new Date().toISOString()).slice(0, 16),
      effective_to: row?.effective_to?.slice(0, 16),
    })
    setEditing(true)
  }

  return <Modal open title="组织关系和主部门" onCancel={close} footer={null} width={680}>
    <ErrorNotice error={rows.error}/><ErrorNotice error={organizations.error}/>
    <Space wrap><Button onClick={() => edit()}>新增组织关系</Button>
      <OrganizationManagers organizations={organizations.data ?? []}/></Space>
    <Table<Membership> rowKey="id" size="small" dataSource={rows.data || []} pagination={false} columns={[
      {title: '组织', dataIndex: 'org_name'},
      {title: '状态', render: (_, row) => row.status === 'active' ? '启用' : '停用'},
      {title: '主部门', render: (_, row) => row.primary ? '是' : '—'},
      {title: '操作', render: (_, row) => <Button type="link" onClick={() => edit(row)}>编辑</Button>},
    ]}/>
    {editing && <>
      <ErrorNotice error={save.error}/>
      <Form form={form} layout="vertical" onFinish={values => save.mutate(values)}>
        <Form.Item name="org_id" label="组织" rules={[{required: true}]}>
          <Select showSearch optionFilterProp="label" options={(organizations.data || []).map(o => ({value: o.id, label: o.org_name}))}/>
        </Form.Item>
        <Form.Item name="status" label="状态" rules={[{required: true}]}>
          <Select options={[{value: 'active', label: '启用'}, {value: 'inactive', label: '停用'}]}/>
        </Form.Item>
        <Form.Item name="effective_from" label="生效时间（UTC）" rules={[{required: true}]}><Input type="datetime-local"/></Form.Item>
        <Form.Item name="effective_to" label="结束时间（UTC）"><Input type="datetime-local"/></Form.Item>
        <Form.Item name="primary" label="设为主部门" valuePropName="checked"><Switch/></Form.Item>
        <Space><Button type="primary" htmlType="submit" loading={save.isPending}>保存组织关系</Button>
        <Button onClick={() => setEditing(false)}>取消编辑</Button></Space>
      </Form>
    </>}
  </Modal>
}


function OrganizationManagers({organizations}: {organizations: {id: number; org_name: string; manager_id: number | null}[]}) {
  const [open, setOpen] = useState(false)
  const [orgId, setOrgId] = useState<number>()
  const [managerId, setManagerId] = useState<number | null>(null)
  const cache = useQueryClient()
  const managers = useQuery({
    queryKey: [endpoint, 'manager-options'], enabled: open,
    queryFn: () => api<{id: number; real_name: string}[]>(endpoint + '/manager-options'),
  })
  const save = useMutation({
    mutationFn: (id: number) => api(endpoint + '/' + id + '/manager', {method: 'PUT', body: {manager_id: managerId}}),
    onSuccess: () => {void cache.invalidateQueries({queryKey: [endpoint, 'membership-options']}); setOpen(false)},
  })
  return <>
    <Button onClick={() => {setOrgId(undefined); setManagerId(null); save.reset(); setOpen(true)}}>配置组织主管</Button>
    <Modal open={open} title="配置组织主管" onCancel={() => setOpen(false)}
      okText="保存主管" confirmLoading={save.isPending} okButtonProps={{disabled: orgId === undefined || managers.isError}}
      onOk={() => {if (orgId !== undefined) save.mutate(orgId)}}>
      <ErrorNotice error={managers.error || save.error}/>
      <Form layout="vertical">
        <Form.Item label="组织">
          <Select showSearch optionFilterProp="label" value={orgId}
            options={organizations.map(org => ({value: org.id, label: org.org_name}))}
            onChange={id => {setOrgId(id); setManagerId(organizations.find(org => org.id === id)?.manager_id ?? null)}}/>
        </Form.Item>
        <Form.Item label="主管">
          <Select showSearch optionFilterProp="label" allowClear loading={managers.isFetching} value={managerId ?? undefined}
            placeholder="选择主管，留空表示取消分配"
            options={(managers.data ?? []).map(manager => ({value: manager.id, label: manager.real_name}))}
            onChange={value => setManagerId(value ?? null)}/>
        </Form.Item>
      </Form>
    </Modal>
  </>
}
