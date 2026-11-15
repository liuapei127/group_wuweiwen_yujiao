import {useState} from 'react'
import {App, Form, Input, Modal, Typography} from 'antd'
import {api} from '../lib/api'
import {ErrorNotice} from './shared'

type Props = {
  accountType: '员工' | '官网'
  username: string
  path: string
  onClose: () => void
  onSuccess?: () => void
}

type Fields = {new_password: string; confirmation: string}

export function PasswordResetDialog({accountType, username, path, onClose, onSuccess}: Props) {
  const [form] = Form.useForm<Fields>()
  const {message} = App.useApp()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>()

  async function save({new_password}: Fields) {
    if (busy) return
    setBusy(true)
    setError(undefined)
    try {
      await api(path, {method: 'POST', body: {new_password}})
    } catch (failure) {
      setError(failure)
      setBusy(false)
      return
    }
    form.resetFields()
    void message.success('密码已重置，该账号需重新登录')
    onClose()
    onSuccess?.()
  }

  return <Modal title={'重置' + accountType + '密码'} open onCancel={onClose} onOk={() => form.submit()}
    okText="确认重置" cancelText="取消" confirmLoading={busy} cancelButtonProps={{disabled: busy}}
    closable={!busy} keyboard={!busy} mask={{closable: !busy}} width={460}>
    <Typography.Paragraph>
      {accountType}账号 <Typography.Text strong>{username}</Typography.Text> 的所有登录会话将失效。
    </Typography.Paragraph>
    <ErrorNotice error={error}/>
    <Form form={form} name="admin-password-reset" layout="vertical" disabled={busy} onFinish={save}>
      <Form.Item name="new_password" label="新密码" extra="12 至 128 个字符" rules={[
        {required: true, message: '请输入新密码'},
        {min: 12, max: 128, message: '请输入 12 至 128 个字符'},
      ]}>
        <Input.Password autoComplete="new-password"/>
      </Form.Item>
      <Form.Item name="confirmation" label="确认新密码" dependencies={['new_password']} rules={[
        {required: true, message: '请再次输入新密码'},
        ({getFieldValue}) => ({
          validator: (_, value: string | undefined) => !value || value === getFieldValue('new_password')
            ? Promise.resolve() : Promise.reject(new Error('两次输入的密码不一致')),
        }),
      ]}>
        <Input.Password autoComplete="new-password"/>
      </Form.Item>
    </Form>
  </Modal>
}
