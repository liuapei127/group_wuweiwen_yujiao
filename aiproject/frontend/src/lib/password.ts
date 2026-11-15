import type {Rule} from 'antd/es/form'
import {mobileNumberPattern} from './mobile'

export const passwordHelp = '8–128 位，至少包含大写字母、小写字母、数字、符号中的两类。不可包含空格、中文或不可见字符。'

export function newPasswordRules(username?: string, contact?: string): Rule[] {
  return [
    {required: true, message: '请输入密码'},
    {
      validator: (_, password?: string) => {
        if (!password) return Promise.resolve()
        const groups = [/[A-Z]/, /[a-z]/, /[0-9]/, /[^a-zA-Z0-9]/]
        const phone = contact?.trim() || ''
        if (password.length < 8 || password.length > 128) {
          return Promise.reject(new Error('密码长度须为 8–128 位'))
        }
        if (/[^!-~]/.test(password)) {
          return Promise.reject(new Error('密码只能使用英文字母、数字和常见英文符号'))
        }
        if (groups.filter(group => group.test(password)).length < 2) {
          return Promise.reject(new Error('密码至少包含两类字符'))
        }
        if (password.toLowerCase() === username?.trim().toLowerCase() ||
            (mobileNumberPattern.test(phone) && password === phone)) {
          return Promise.reject(new Error('新密码不能与登录账号或手机号相同'))
        }
        return Promise.resolve()
      },
    },
  ]
}
