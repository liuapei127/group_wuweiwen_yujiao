import {useState} from 'react'
import {App, Form, Modal, Typography} from 'antd'
import {api} from '../lib/api'
import {mobileNumberPattern} from '../lib/mobile'
import {ErrorNotice} from './shared'
import {PasswordFields} from './PasswordFields'

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

  const resetToMobileSuffix = mobileNumberPattern.test(username)

  async function save(password?: string) {
    if (busy) return
    setBusy(true)
    setError(undefined)
    try {
      await api(path, {method: 'POST', body: password === undefined ? {} : {new_password: password}})
    } catch (failure) {
      setError(failure)
      setBusy(false)
      return
    }
    if (!resetToMobileSuffix) form.resetFields()
    void message.success('密码已重置，该账号需重新登录')
    onClose()
    onSuccess?.()
  }

  return <Modal title={'重置' + accountType + '密码'} open onCancel={onClose} onOk={() => resetToMobileSuffix ? void save() : form.submit()}
    okText="确认重置" cancelText="取消" confirmLoading={busy} cancelButtonProps={{disabled: busy}}
    closable={!busy} keyboard={!busy} mask={{closable: !busy}} width={460}>
    <Typography.Paragraph>
      {accountType}账号 <Typography.Text strong>{username}</Typography.Text> 的所有登录会话将失效。
    </Typography.Paragraph>
    <ErrorNotice error={error}/>
    {resetToMobileSuffix ? <Typography.Paragraph>密码将自动重置为手机号后 6 位。</Typography.Paragraph> :
      <Form form={form} name="admin-password-reset" layout="vertical" disabled={busy} onFinish={values => void save(values.new_password)}>
        <PasswordFields username={username}/>
      </Form>}
  </Modal>
}
