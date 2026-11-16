import {useState} from 'react'
import {App, Button, Card, Checkbox, Input, InputNumber, Modal, Select, Space, Table, Tag, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ErrorNotice, PageTitle} from '../components/shared'
import {PasswordResetDialog} from '../components/PasswordResetDialog'
import {api, query} from '../lib/api'

type Account = {
  id: number; username: string; name: string; contact: string
  student_id: number | null; student_enabled: boolean; crm_lead_id?: number | null
}
type Region = "Singapore" | "Germany"
type StudentOption = {id: number; real_name: string}
const endpoint = '/api/v1/enterprise/website-accounts'
const pageSize = 20

export function WebsiteAccounts() {
  const {user} = useAuth()
  const {message} = App.useApp()
  const cache = useQueryClient()
  const [keyword, setKeyword] = useState('')
  const [after, setAfter] = useState(0)
  const [selected, select] = useState<Account>()
  const [passwordTarget, setPasswordTarget] = useState<Account>()
  const [customerTarget, setCustomerTarget] = useState<Account>()
  const [studentId, setStudentId] = useState<number>()
  const [studentKeyword, setStudentKeyword] = useState('')
  const [create, setCreate] = useState(false)
  const [teacherId, setTeacherId] = useState<number>()
  const [teacherKeyword, setTeacherKeyword] = useState('')
  const [country, setCountry] = useState<Region>()
  const scope = [user?.id, 'website-accounts']
  const accounts = useQuery({
    queryKey: [...scope, keyword, after],
    queryFn: () => api<Account[]>(endpoint + query({keyword, after_id: after, limit: pageSize})),
  })
  const students = useQuery({
    queryKey: [...scope, 'students', studentKeyword],
    enabled: !!selected && selected.student_id === null && !create,
    queryFn: () => api<StudentOption[]>(endpoint + '/students' + query({keyword: studentKeyword, limit: 50})),
  })
  const teachers = useQuery({
    queryKey: [...scope, 'teachers', teacherKeyword],
    enabled: !!selected && create,
    queryFn: () => api<StudentOption[]>(endpoint + '/teachers' + query({keyword: teacherKeyword, limit: 50})),
  })
  const update = useMutation({
    mutationFn: ({account, options}: {
      account: Account
      options: {student: number} | {teacher: number; country: Region}
    }) => api<Account>(
      endpoint + '/' + account.id + '/student-access',
      'student' in options
        ? {method: 'PUT', body: {student_id: options.student, enabled: !account.student_enabled}}
        : {method: 'POST', body: {class_teacher_id: options.teacher, abroad_country: options.country}},
    ),
    onSuccess: account => {
      select(undefined)
      void cache.invalidateQueries({queryKey: scope})
      void message.success(account.student_enabled ? '已开通学生身份' : '已关闭学生身份')
    },
  })

  function open(account: Account) {
    update.reset()
    setStudentKeyword('')
    setTeacherKeyword('')
    setTeacherId(undefined)
    setCountry(undefined)
    setCreate(false)
    setStudentId(account.student_id ?? undefined)
    select(account)
  }

  return <>
    <PageTitle title="官网账号" description="重置官网账号密码，创建或关联学生档案并管理学生身份。"
      extra={<Input.Search aria-label="搜索官网账号" placeholder="搜索官网手机号或姓名" maxLength={64}
        onSearch={value => {setAfter(0); setKeyword(value.trim())}} allowClear/>}/>
    <ErrorNotice error={accounts.error}/>
    <Card>
      <Table rowKey="id" dataSource={accounts.data || []} loading={accounts.isFetching} pagination={false}
        scroll={{x: 765}} locale={{emptyText: '暂无官网账号'}} columns={[
          {title: '官网账号', dataIndex: 'username'},
          {title: '姓名', dataIndex: 'name'},
          {title: '联系方式', dataIndex: 'contact'},
          {title: '官网身份', render: (_, account) => <Tag>{account.student_enabled ? '学生已开通' : '游客'}</Tag>},
          {title: '学生档案编号', render: (_, account) => account.student_id ?? '—'},
          {title: '客户档案编号', render: (_, account) => account.crm_lead_id ?? '—'},
          {title: '操作', width: 232, render: (_, account) => <Space wrap size={0}>
            <Button type="link" onClick={() => open(account)}>
              {account.student_enabled ? '关闭学生身份' : '开通学生身份'}
            </Button>
            <Button type="link" onClick={() => setPasswordTarget(account)}>重置密码</Button>
            {user?.role_code === 'admin' && <Button type="link" onClick={() => setCustomerTarget(account)}>
              {account.crm_lead_id ? '核验客户身份' : '关联客户档案'}
            </Button>}
          </Space>},
        ]}/>
      <Space style={{marginTop: 12}}>
        <Button disabled={!after || accounts.isFetching} onClick={() => setAfter(0)}>返回首批</Button>
        <Button disabled={accounts.data?.length !== pageSize || accounts.isFetching}
          onClick={() => setAfter(accounts.data?.at(-1)?.id ?? after)}>查看更多</Button>
      </Space>
    </Card>
    <Modal title={selected?.student_enabled ? '关闭学生身份' : '开通学生身份'}
      open={!!selected} onCancel={() => {if (!update.isPending) select(undefined)}}
      confirmLoading={update.isPending} okButtonProps={{disabled: create ? !teacherId || !country : !studentId}}
      onOk={() => {
        if (!selected) return
        if (create && teacherId && country) update.mutate({account: selected, options: {teacher: teacherId, country}})
        if (!create && studentId) update.mutate({account: selected, options: {student: studentId}})
      }}>
      <Typography.Paragraph>官网账号 {selected?.username} 的登录手机号和密码照旧。保存后需重新登录官网。</Typography.Paragraph>
      {selected?.student_id === null && <Space wrap style={{marginBottom: 12}}>
        <Button type={!create ? "primary" : "default"} disabled={update.isPending} onClick={() => {update.reset(); setCreate(false)}}>关联已有档案</Button>
        <Button type={create ? "primary" : "default"} disabled={update.isPending} onClick={() => {update.reset(); setCreate(true)}}>新建学生档案</Button>
      </Space>}
      {selected?.student_id === null && create ? <Space orientation="vertical" style={{width: "100%"}}>
        <label htmlFor="website-teacher">班主任</label>
        <Select id="website-teacher" showSearch={{filterOption: false, onSearch: setTeacherKeyword}}
          options={(teachers.data || []).map(row => ({value: row.id, label: row.real_name + ' · 员工 ' + row.id}))}
          value={teacherId} onChange={setTeacherId} loading={teachers.isFetching} disabled={update.isPending}
          placeholder="按姓名搜索班主任" style={{width: "100%"}}/>
        <ErrorNotice error={teachers.error}/>
        <label htmlFor="website-country">留学地区</label>
        <Select id="website-country" value={country} onChange={setCountry} disabled={update.isPending}
          options={[{value: "Singapore", label: "新加坡"}, {value: "Germany", label: "德国"}]}
          placeholder="选择留学地区" style={{width: "100%"}}/>
      </Space> : selected?.student_id === null ? <>
        <label htmlFor="website-student">关联企业学生档案</label>
        <Select id="website-student" showSearch={{filterOption: false, onSearch: setStudentKeyword}}
          options={(students.data || []).map(row => ({value: row.id, label: row.real_name + ' · 档案 ' + row.id}))}
          value={studentId} onChange={setStudentId} loading={students.isFetching} disabled={update.isPending}
          placeholder="输入姓名搜索企业学生档案" style={{width: '100%'}}/>
        <ErrorNotice error={students.error}/>
      </> : <Typography.Paragraph>关联学生档案 {selected?.student_id}</Typography.Paragraph>}
      <ErrorNotice error={update.error}/>
    </Modal>
    {customerTarget && <CustomerAdministration key={customerTarget.id} account={customerTarget}
      onClose={() => setCustomerTarget(undefined)} onSaved={() => void cache.invalidateQueries({queryKey: scope})}/>}
    {passwordTarget && <PasswordResetDialog accountType="官网" username={passwordTarget.username}
      path={endpoint + '/' + passwordTarget.id + '/password'} onClose={() => setPasswordTarget(undefined)}/>}
  </>
}

function CustomerAdministration({account, onClose, onSaved}: {account: Account; onClose: () => void; onSaved: () => void}) {
  const {message} = App.useApp()
  const [linked, setLinked] = useState(account.crm_lead_id)
  const [binding, setBinding] = useState<'existing' | 'create'>('existing')
  const [leadId, setLeadId] = useState<number>()
  const [name, setName] = useState('')
  const [mobile, setMobile] = useState('')
  const [checked, setChecked] = useState(false)
  const attach = useMutation({
    mutationFn: () => api<{lead_id: number}>(endpoint + '/' + account.id + '/customer', {
      method: 'PUT', body: binding === 'create' ? {create: true} : {lead_id: leadId},
    }),
    onSuccess: result => {
      setLinked(result.lead_id)
      onSaved()
      void message.success('客户档案已关联')
    },
  })
  const verify = useMutation({
    mutationFn: () => api(endpoint + '/customers/' + linked + '/identity', {
      method: 'PUT', body: {name: name.trim(), mobile: mobile.trim(), confirmed: checked},
    }),
    onSuccess: () => {
      void message.success('已登记核验信息')
      onClose()
    },
  })
  const busy = attach.isPending || verify.isPending
  const verified = checked && !!name.trim() && /^1[3-9][0-9]{9}$/.test(mobile.trim())
  return <Modal open title={linked ? '登记客户身份核验' : '关联客户档案'} onCancel={onClose}
    closable={!busy} keyboard={!busy} mask={{closable: !busy}} cancelButtonProps={{disabled: busy}}
    width={535} okText={linked ? '保存核验' : '确认关联'} confirmLoading={busy}
    okButtonProps={{disabled: linked ? !verified : binding === 'existing' && !leadId}}
    onOk={() => linked ? verify.mutate() : attach.mutate()}>
    <Space orientation="vertical" style={{width: '100%'}}>
      <Typography.Text>官网账号　{account.username}</Typography.Text>
      {linked ? <>
        <Typography.Text>客户档案编号　{linked}</Typography.Text>
        <Input aria-label="已核实姓名" placeholder="已核实姓名" maxLength={64} value={name} disabled={busy}
          onChange={event => setName(event.target.value)}/>
        <Input aria-label="已核实手机号" placeholder="已核实本人手机号" inputMode="tel" maxLength={11} value={mobile}
          disabled={busy} onChange={event => setMobile(event.target.value)}/>
        <Checkbox disabled={busy} checked={checked} onChange={event => setChecked(event.target.checked)}>
          我已独立核实姓名和本人手机号
        </Checkbox>
      </> : <>
        <Typography.Text>由顾问先跟进该游客，档案将归该顾问。</Typography.Text>
        <Select value={binding} onChange={setBinding} disabled={busy} style={{width: '100%'}}
          options={[{value: 'existing', label: '关联顾问名下的已有客户'}, {value: 'create', label: '由管理员建档并关联'}]}/>
        {binding === 'existing' && <InputNumber aria-label="已有客户编号" placeholder="填写已有客户编号"
          min={1} precision={0} value={leadId} disabled={busy} onChange={id => setLeadId(id ?? undefined)} style={{width: '100%'}}/>}
      </>}
      <ErrorNotice error={attach.error || verify.error}/>
    </Space>
  </Modal>
}
