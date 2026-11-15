import {useState} from 'react'
import {App, Form, Input, Modal, Typography} from 'antd'
import {ErrorNotice} from './shared'
import {PasswordFields} from './PasswordFields'

export type PasswordChange = {old_password: string; new_password: string}

type Props = {
  username?: string
  contact?: string
  submit: (passwords: PasswordChange) => Promise<unknown>
  onClose: () => void
  onChanged: () => void
}

export function PasswordChangeDialog({username, contact, submit, onClose, onChanged}: Props) {
  const [form] = Form.useForm<PasswordChange & {confirmation: string}>()
  const {message} = App.useApp()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>()

  async function save({old_password, new_password}: PasswordChange) {
    if (busy) return
    setBusy(true)
    setError(undefined)
    try {
      await submit({old_password, new_password})
    } catch (failure) {
      setError(failure)
      setBusy(false)
      return
    }
    form.resetFields()
    void message.success('密码已修改，请使用新密码重新登录')
    onClose()
    onChanged()
  }

  return <Modal title="修改密码" open centered width={460} onCancel={onClose} onOk={() => form.submit()}
    okText="保存密码" cancelText="取消" confirmLoading={busy} cancelButtonProps={{disabled: busy}}
    closable={!busy} keyboard={!busy} mask={{closable: !busy}}>
    <Typography.Paragraph>修改成功后，所有登录会话均需重新登录。</Typography.Paragraph>
    <ErrorNotice error={error}/>
    <Form form={form} name="change-password" layout="vertical" disabled={busy} onFinish={save}>
      <Form.Item name="old_password" label="当前密码" rules={[{required: true, message: '请输入当前密码'}]}>
        <Input.Password autoComplete="current-password" maxLength={256}/>
      </Form.Item>
      <PasswordFields username={username} contact={contact}/>
    </Form>
  </Modal>
}
