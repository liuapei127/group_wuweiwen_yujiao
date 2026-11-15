import {Form, Input} from 'antd'
import {newPasswordRules, passwordHelp} from '../lib/password'

export function PasswordFields({username, contact}: {username?: string; contact?: string}) {
  return <>
    <Form.Item name="new_password" label="新密码" extra={passwordHelp} rules={newPasswordRules(username, contact)}>
      <Input.Password autoComplete="new-password" maxLength={128}/>
    </Form.Item>
    <Form.Item name="confirmation" label="确认新密码" dependencies={['new_password']} rules={[
      {required: true, message: '请再次输入新密码'},
      ({getFieldValue}) => ({
        validator: (_, value: string | undefined) => !value || value === getFieldValue('new_password')
          ? Promise.resolve() : Promise.reject(new Error('两次输入的密码不一致')),
      }),
    ]}>
      <Input.Password autoComplete="new-password" maxLength={128}/>
    </Form.Item>
  </>
}
