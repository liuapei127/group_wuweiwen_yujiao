import {expect, test} from '@playwright/test'
import {fileURLToPath} from 'node:url'
import {loadEnv} from 'vite'

// Mock authentication calls without recording local demo credentials in traces.
test.use({serviceWorkers: 'block', trace: 'off'})
const demoConfig = loadEnv('development', fileURLToPath(new URL('..', import.meta.url)))

test.describe('local test login shortcuts', () => {
  const quickLoginRoles = [
    {role:'管理员',code:'admin',key:'ADMIN'},
    {role:'顾问',code:'employee',key:'ADVISOR'},
    {role:'主管',code:'manager',key:'MANAGER'},
    {role:'班主任',code:'team_leader',key:'TEACHER'},
  ].map(account => ({...account,
    username: demoConfig['VITE_' + account.key + '_TEST_USERNAME'],
    password: demoConfig['VITE_' + account.key + '_TEST_PASSWORD'],
  }))
  for (const account of quickLoginRoles) {
    test('local quick login authenticates '+account.code+' through the normal API', async ({page}) => {
      await page.route('**/api/v1/auth/status', route => route.fulfill({json:{code:0,data:{ready:true}}}))
      const shortcut = page.getByRole('button',{name:new RegExp('^'+account.role+'一键登录')})
      if (!account.username || !account.password) {
        await page.goto('/')
        await expect(shortcut).toHaveCount(0)
        return
      }
      let loginCalls = 0
      await page.route('**/api/v1/**', async route => {
        const path = new URL(route.request().url()).pathname
        const reply = (data:unknown) => route.fulfill({json:{code:0,data}})
        if (path === '/api/v1/auth/status') return reply({mode:'base_rs256',ready:true})
        if (path === '/api/v1/auth/login') {
          loginCalls += 1
          const body = route.request().postDataJSON()
          expect(body.username === account.username && body.password === account.password).toBe(true)
          return reply({access_token:'test-'+account.code,user:{id:1,username:account.username,
            real_name:'快捷测试'+account.role,role_code:account.code,role_name:account.role,
            permissions:['dashboard:read'],student_ids:[]}})
        }
        return reply({})
      })
      await page.goto('/customers/757')
      await page.getByLabel('员工手机号').fill('15072228372')
      await page.getByLabel('登录密码').fill('wrong-password')
      await shortcut.click()
      await expect(page.locator('.user-menu')).toContainText('快捷测试'+account.role)
      await expect(page).toHaveURL(/\/dashboard$/)
      expect(loginCalls).toBe(1)
    })
  }

  test('local quick login shows backend rejection and lets the user retry', async ({page}) => {
    test.skip(!quickLoginRoles.filter(account => ['ADVISOR', 'MANAGER'].includes(account.key)).every(account => account.username && account.password), 'Both demo accounts are required for this scenario')
    await page.route('**/api/v1/auth/status', route => route.fulfill({json:{code:0,data:{ready:true}}}))
    await page.route('**/api/v1/auth/login', route => route.fulfill({status:401,json:{detail:'测试账号密码已变更'}}))
    await page.goto('/')
    await page.getByRole('button',{name:'顾问一键登录',exact:true}).click()
    await expect(page.getByText('测试账号密码已变更',{exact:true})).toBeVisible()
    await expect(page.getByRole('heading',{name:'登录你的工作空间'})).toBeVisible()
    await expect(page.getByLabel('员工手机号')).toHaveValue('')
    await expect(page.getByRole('button',{name:'主管一键登录',exact:true})).toBeEnabled()
  })
})

test.describe('website demo shortcuts', () => {
  for (const {key, name, type, destination} of [
    {key: 'VISITOR', name: '游客', type: 'visitor', destination: /\/website\/visitor\/services$/},
    {key: 'STUDENT', name: '学生', type: 'student', destination: /\/website\/student$/},
  ]) {
    test(name + ' shortcut logs in and opens its services', async ({page}) => {
      const username = demoConfig['VITE_' + key + '_TEST_USERNAME']
      const password = demoConfig['VITE_' + key + '_TEST_PASSWORD']
      let loginRequests = 0
      await page.route('**/api/v1/**', route => {
        const path = new URL(route.request().url()).pathname
        const reply = (data: unknown) => route.fulfill({json: {code: 0, data}})
        if (path === '/api/v1/visitors/login') {
          loginRequests++
          const body = route.request().postDataJSON()
          expect(body.username === username && body.password === password).toBe(true)
          return reply({access_token: type + '-demo-token', account_type: type})
        }
        if (path === '/api/v1/visitors/me') return reply({account_type: type})
        if (path === '/api/v1/visitors/profile') return reply({
          username, name: '演示账号', contact: username, account_type: type, created_at: '2026-11-18T00:00:00Z',
        })
        if (path === '/api/v1/student/assistant/overview') return reply({profile: {}})
        return reply([])
      })
      await page.goto('/website')
      await page.getByRole('button', {name: /^登\s*录$/}).click()
      const modal = page.getByRole('dialog', {name: '官网登录', exact: true})
      const shortcut = modal.getByRole('button', {name: name + '一键登录', exact: true})
      if (!username || !password) {
        await expect(shortcut).toHaveCount(0)
        await expect(modal.getByLabel('手机号')).toBeVisible()
        return
      }
      await shortcut.click()
      await expect(page).toHaveURL(destination)
      await expect(modal).toBeHidden()
      if (type === 'visitor') await expect(page.getByRole('region', {name: '游客服务'})).toBeVisible()
      expect(loginRequests).toBe(1)
    })
  }
})
