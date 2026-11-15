import {useRef, useState} from 'react'
import {DownOutlined, UserOutlined} from '@ant-design/icons'
import {App, Avatar, Button, Descriptions, Modal, Space, Spin, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {ErrorNotice} from '../components/shared'

type Profile = {
  username: string
  name: string
  contact: string
  account_type: 'visitor' | 'student'
  created_at: string
  avatar_url: string | null
}

type Props = {
  token: string
  request: <T,>(path: string, method?: string, body?: unknown) => Promise<T>
  signingOut: boolean
  onChangePassword: () => void
  onSignOut: () => void
}

const maxAvatarBytes = 2 * 1024 * 1024
const dateFormat = new Intl.DateTimeFormat('zh-CN', {dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Shanghai'})

export function WebsiteAccountMenu({token, request, signingOut, onChangePassword, onSignOut}: Props) {
  const [open,setOpen] = useState(false)
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
  const account = profile.data
  const avatar = (size: number) => <Avatar size={size} src={account?.avatar_url} icon={<UserOutlined/>}
    className="website-account-avatar"/>

  return <>
    <Button className="website-account-trigger" icon={avatar(24)} aria-haspopup="dialog" onClick={() => setOpen(true)}>
      个人信息 <DownOutlined/>
    </Button>
    <Modal title="个人信息" open={open} onCancel={() => setOpen(false)} centered width={480}
      footer={<Space wrap>
        <Button disabled={upload.isPending || signingOut} onClick={() => {setOpen(false); onChangePassword()}}>修改密码</Button>
        <Button danger disabled={upload.isPending} loading={signingOut} onClick={onSignOut}>退出登录</Button>
      </Space>}>
      <ErrorNotice error={profile.error}/>
      {profile.isLoading && <Spin/>}
      {account && <>
        <div className="website-account-picture">
          {avatar(68)}
          <div>
            <Button onClick={() => picker.current?.click()} loading={upload.isPending}>更换头像</Button>
            <Typography.Paragraph type="secondary">JPG、PNG 或 WebP，最大 2 MB</Typography.Paragraph>
            <input ref={picker} type="file" hidden accept="image/jpeg,image/png,image/webp" aria-label="选择头像图片"
              onChange={event => {
                const file = event.target.files?.[0]
                event.target.value = ''
                if (!file) return
                if (file.size > maxAvatarBytes) {
                  void message.error('头像文件不能超过 2 MB')
                  return
                }
                upload.mutate(file)
              }}/>
          </div>
        </div>
        <ErrorNotice error={upload.error}/>
        <Descriptions column={1} items={[
          {key:'username',label:'登录账号',children:account.username},
          {key:'name',label:'姓名',children:account.name},
          {key:'contact',label:'联系方式',children:account.contact},
          {key:'type',label:'账号身份',children:account.account_type === 'student' ? '学生' : '游客'},
          {key:'created',label:'注册时间（北京时间）',children:dateFormat.format(new Date(account.created_at))},
        ]}/>
      </>}
    </Modal>
  </>
}
