import {expect, test, type Page} from '@playwright/test'

async function openLogin(page: Page) {
  await page.route('**/api/v1/website/sections', route => route.fulfill({json: {code: 0, data: []}}))
  await page.goto('/website')
  await page.getByRole('button', {name: /^登\s*录$/}).click()
  const dialog = page.getByRole('dialog', {name: '官网登录'})
  await dialog.getByLabel('手机号', {exact: true}).fill('13900009101')
  await dialog.getByLabel('密码').fill('test-password')
  return dialog
}

test('website login reports an unavailable service and can retry after recovery', async ({page}) => {
  let recovered = false
  await page.route('**/api/v1/visitors/login', route => {
    expect(route.request().postDataJSON()).toEqual({username: '13900009101', password: 'test-password'})
    return recovered ? route.fulfill({json: {code: 0, data: {access_token: 'visitor-test', account_type: 'visitor'}}})
      : route.fulfill({status: 500, contentType: 'text/plain', body: ''})
  })
  await page.route('**/api/v1/visitors/me', route => route.fulfill({json: {code: 0, data: {account_type: 'visitor'}}}))
  await page.route('**/api/v1/visitors/profile', route => route.fulfill({json: {code: 0, data: {
    username: '13900009101', name: '测试游客', contact: '13900009101',
    account_type: 'visitor', created_at: '2026-11-15T07:00:00Z', avatar_url: null,
  }}}))
  const dialog = await openLogin(page)
  const login = dialog.getByRole('button', {name: /登\s*录$/})
  for (let attempt = 0; attempt < 2; attempt++) {
    const reply = page.waitForResponse(response => response.url().endsWith('/api/v1/visitors/login'))
    await login.click()
    await reply
    await expect(page.getByText('服务暂时不可用，请稍后重试。', {exact: true})).toBeVisible()
    await expect(page.getByText('服务暂时不可用，请稍后重试。', {exact: true})).toHaveCount(1)
    await expect(login).toBeEnabled()
  }
  await expect(dialog).toBeVisible()
  await expect(dialog.getByLabel('手机号', {exact: true})).toHaveValue('13900009101')
  await expect(dialog.getByLabel('密码')).toHaveValue('test-password')
  recovered = true
  await login.click()
  await expect(page).toHaveURL(/\/website\/visitor$/)
  await expect(dialog).toBeHidden()
  await expect(page.getByText('服务暂时不可用，请稍后重试。', {exact: true})).toBeHidden()
})

test('website login reports a connection failure', async ({page}) => {
  await page.route('**/api/v1/visitors/login', route => route.abort('connectionrefused'))
  const dialog = await openLogin(page)
  await dialog.getByRole('button', {name: /^登\s*录$/}).click()
  await expect(page.getByText('无法连接服务，请稍后重试。', {exact: true})).toBeVisible()
  await expect(dialog).toBeVisible()
})

test('website login preserves the password validation message', async ({page}) => {
  await page.route('**/api/v1/visitors/login', route => route.fulfill({
    status: 401, json: {detail: '手机号或密码不正确'},
  }))
  const dialog = await openLogin(page)
  await dialog.getByRole('button', {name: /^登\s*录$/}).click()
  await expect(page.getByText('手机号或密码不正确', {exact: true})).toBeVisible()
  await expect(dialog).toBeVisible()
})

test('website login rejects an invalid success response', async ({page}) => {
  await page.route('**/api/v1/visitors/login', route => route.fulfill({
    status: 200, contentType: 'text/html', body: '<html>Proxy unavailable</html>',
  }))
  const dialog = await openLogin(page)
  await dialog.getByRole('button', {name: /^登\s*录$/}).click()
  await expect(page.getByText('服务响应异常，请稍后重试。', {exact: true})).toBeVisible()
  await expect(dialog).toBeVisible()
})
