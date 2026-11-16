import {useRef, useState} from 'react'
import {DownOutlined, UserOutlined} from '@ant-design/icons'
import {App, Avatar, Button, Descriptions, Form, Input, Modal, Space, Spin, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {ErrorNotice} from '../components/shared'

type Profile = {
  version?: number | null
  username: string
  name: string
  nickname?: string | null
  contact: string
  account_type: 'visitor' | 'student'
  created_at: string
  avatar_url: string | null
}

type ProfileFields = {nickname: string; name: string; contact: string}

type Props = {
  token: string
  request: <T,>(path: string, method?: string, body?: unknown) => Promise<T>
  signingOut: boolean
  onViewCustomer: () => void
  onChangePassword: () => void
  onSignOut: () => void
}

const maxAvatarBytes = 2 * 1024 * 1024
const dateFormat = new Intl.DateTimeFormat('zh-CN', {dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai'})

export function WebsiteAccountMenu({token, request, signingOut, onViewCustomer, onChangePassword, onSignOut}: Props) {
  const [open, setOpen] = useState(false)
  const [editing, setEditing] = useState(false)
  const [form] = Form.useForm<ProfileFields>()
  const [editVersion, setEditVersion] = useState<number | null>()
  const picker = useRef<HTMLInputElement>(null)
  const cache = useQueryClient()
  const {message} = App.useApp()
  const key = ['visitor', 'profile', token]
  const profile = useQuery({
    queryKey: key,
    queryFn: () => request<Profile>('/api/v1/visitors/profile'),
  })
  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return request<Profile>('/api/v1/visitors/avatar', 'PUT', form)
    },
    onSuccess: updated => {
      cache.setQueryData(key, updated)
      void message.success('头像已更新')
    },
  })
  const save = useMutation({
    mutationFn: (fields: ProfileFields) => request<Profile>('/api/v1/visitors/profile', 'PUT', {...fields, expected_version: editVersion}),
    onSuccess: updated => {
      cache.setQueryData(key, updated)
      setEditing(false)
      void cache.invalidateQueries({queryKey: ['visitor', 'crm-profile', token]})
      void message.success('个人信息已保存')
    },
  })
  const account = profile.data
  const busy = upload.isPending || save.isPending || signingOut

  function cancelEditing() {
    setEditing(false)
    save.reset()
    upload.reset()
  }

  function closeProfile() {
    if (busy) return
    cancelEditing()
    setOpen(false)
  }
  const avatar = (size: number) => <Avatar size={size} src={account?.avatar_url} icon={<UserOutlined/>}
    className="website-account-avatar"/>

  return <>
    <Button className="website-account-trigger" icon={avatar(24)} aria-haspopup="dialog" onClick={() => setOpen(true)}>
      个人信息 <DownOutlined/>
    </Button>
    <Modal title="个人信息" open={open} onCancel={closeProfile} centered width={480}
      closable={!busy} keyboard={!busy} mask={{closable: !busy}}
      footer={editing ? <Space key="editing" wrap>
        <Button disabled={busy} onClick={cancelEditing}>取消编辑</Button>
        <Button type="primary" disabled={upload.isPending} loading={save.isPending} onClick={() => form.submit()}>保存</Button>
      </Space> : <Space key="viewing" wrap>
        <Button type="primary" disabled={!account || busy} onClick={() => {setEditVersion(account?.version); setEditing(true)}}>编辑资料</Button>
        <Button disabled={busy} onClick={() => {closeProfile(); onViewCustomer()}}>我的资料</Button>
        <Button disabled={busy} onClick={() => {closeProfile(); onChangePassword()}}>修改密码</Button>
        <Button danger disabled={upload.isPending} loading={signingOut} onClick={onSignOut}>退出登录</Button>
      </Space>}>
      <ErrorNotice error={profile.error}/>
      {profile.isLoading && <Spin/>}
      {account && <>
        <div className="website-account-picture">
          {avatar(68)}
          {editing && <div>
            <Button disabled={save.isPending} onClick={() => picker.current?.click()} loading={upload.isPending}>更换头像</Button>
            <Typography.Paragraph type="secondary">JPG、PNG 或 WebP，最大 2 MB</Typography.Paragraph>
            <input ref={picker} type="file" hidden accept="image/jpeg,image/png,image/webp" aria-label="选择头像图片"
              onChange={event => {
                const file = event.target.files?.[0]
                event.target.value = ''
                if (!file || busy) return
                if (file.size > maxAvatarBytes) {
                  void message.error('头像文件不能超过 2 MB')
                  return
                }
                upload.mutate(file)
              }}/>
          </div>}
        </div>
        {editing ? <>
          <ErrorNotice error={upload.error}/>
          <ErrorNotice error={save.error}/>
          <Form<ProfileFields> form={form} name="website-profile" layout="vertical" clearOnDestroy
            disabled={save.isPending} initialValues={{nickname: account.nickname ?? '', name: account.name, contact: account.contact}}
            onFinish={fields => {if (!busy) save.mutate(fields)}}>
            <Form.Item name="nickname" label="昵称"><Input autoComplete="nickname" maxLength={64}/></Form.Item>
            <Form.Item name="name" label="姓名"><Input autoComplete="name" maxLength={64}/></Form.Item>
            <Form.Item name="contact" label="联系方式"><Input maxLength={128}/></Form.Item>
          </Form>
        </> : <Descriptions column={1} items={[
          {key:'username',label:'登录账号',children:account.username},
          {key:'nickname',label:'昵称',children:account.nickname || '未设置'},
          {key:'name',label:'姓名',children:account.name},
          {key:'contact',label:'联系方式',children:account.contact},
          {key:'type',label:'账号身份',children:account.account_type === 'student' ? '学生' : '游客'},
          {key:'created',label:'注册时间（北京时间）',children:dateFormat.format(new Date(account.created_at))},
        ]}/>}
      </>}
    </Modal>
  </>
}
