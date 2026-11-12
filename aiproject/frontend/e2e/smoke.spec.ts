import {expect,test} from '@playwright/test'

test('login page shows workspace branding (UI-only scope)',async({page})=>{
  await page.goto('/')
  await expect(page.getByRole('heading',{name:'登录你的工作空间'})).toBeVisible()
  await expect(page.getByLabel('员工账号')).toBeVisible()
  await expect(page.getByLabel('登录密码')).toBeVisible()
  await expect(page.getByRole('button',{name:'登录工作台'})).toBeVisible()
})
