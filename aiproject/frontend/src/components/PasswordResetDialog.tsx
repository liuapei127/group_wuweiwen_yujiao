import {useState} from 'react'
import {App, Modal, Typography} from 'antd'
import {api} from '../lib/api'
import {mobileNumberPattern} from '../lib/mobile'
import {ErrorNotice} from './shared'

type Props = {
  accountType: '员工' | '官网'
  username: string
  path: string
  onClose: () => void
  onSuccess?: () => void
}

export function PasswordResetDialog({accountType, username, path, onClose, onSuccess}: Props) {
  const {message} = App.useApp()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<unknown>()

  const isMobileAccount = mobileNumberPattern.test(username)

  async function save() {
    if (busy || !isMobileAccount) return
    setBusy(true)
    setError(undefined)
    try {
      await api(path, {method: 'POST', body: {}})
    } catch (failure) {
      setError(failure)
      setBusy(false)
      return
    }
    void message.success('密码已重置，该账号需重新登录')
    onClose()
    onSuccess?.()
  }

  return <Modal title={'重置' + accountType + '密码'} open onCancel={onClose} onOk={() => void save()}
    okText="确认重置" cancelText="取消" confirmLoading={busy}
    okButtonProps={{disabled: !isMobileAccount}} cancelButtonProps={{disabled: busy}}
    closable={!busy} keyboard={!busy} mask={{closable: !busy}} width={460}>
    <ErrorNotice error={error}/>
    {isMobileAccount ? <>
      <Typography.Paragraph>
        {accountType}账号 <Typography.Text strong>{username}</Typography.Text> 的所有登录会话将失效。
      </Typography.Paragraph>
      <Typography.Paragraph>密码将自动重置为大写 YJ 加手机号后 6 位，共 8 个字符。</Typography.Paragraph>
    </> : <Typography.Paragraph>请先将登录账号迁移为手机号。</Typography.Paragraph>}
  </Modal>
}
