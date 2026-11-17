import {expect, test} from '@playwright/test'

test.use({serviceWorkers: 'block'})

test('guest customer chat resumes in the tab and clears on request', async ({page}) => {
  const requests: {query: string; history?: {role: string; content: string}[]}[] = []
  await page.route('**/api/cs/chat', route => {
    const turn = route.request().postDataJSON()
    requests.push(turn)
    return route.fulfill({json: {code: 0, data: {answer: '客服回复', session_id: 'a'.repeat(64)}}})
  })
  await page.goto('/website')
  const open = page.getByRole('button', {name: '打开粤教升学助手'})
  const question = page.getByRole('textbox', {name: '输入想了解的问题'})
  await open.click()
  await question.fill('我叫测试甲')
  await question.press('Enter')
  await expect(page.getByText('客服回复', {exact: true})).toBeVisible()
  await page.reload()
  await open.click()
  await expect(page.getByText('我叫测试甲', {exact: true})).toBeVisible()
  await question.fill('我叫什么')
  await question.press('Enter')
  await expect.poll(() => requests.length).toBe(2)
  expect(requests[1].history).toEqual([
    {role: 'user', content: '我叫测试甲'}, {role: 'assistant', content: '客服回复'},
  ])
  await page.getByRole('button', {name: '清空对话'}).click()
  await expect(page.getByText('我叫测试甲', {exact: true})).toHaveCount(0)
  expect(await page.evaluate(() => sessionStorage.getItem('website-customer-chat'))).toBeNull()
})

test('a profile event refreshes the displayed screening input', async ({page}) => {
  let version = 3
  let subscribed = false
  let releaseUpdate!: () => void
  const update = new Promise<void>(resolve => {releaseUpdate = resolve})
  await page.addInitScript(() => sessionStorage.setItem('ent-token', 'portrait-ui-test'))
  await page.route('**/api/v1/**', async route => {
    const url = new URL(route.request().url())
    const reply = (data: unknown) => route.fulfill({json: {code: 0, data}})
    if (url.pathname.endsWith('/auth/me')) return reply({
      id: 10, real_name: '测试顾问', role_code: 'advisor', role_name: '顾问', permissions: ['crm:read'], student_ids: [],
    })
    if (url.pathname.endsWith('/profile')) {
      if (url.searchParams.has('watch_version')) {
        subscribed = true
        await update
        return route.fulfill({contentType: 'text/event-stream', body: 'event: result\ndata: {"data":{"changed":true}}\n\n'})
      }
      return reply({version, customer_name: '测试客户', age: 20,
        language_ability: '英语：雅思 6；日语：N2；德语：B1',
        readiness: {ready: false, missing_fields: []},
        screening_input: [{id: 'U_010', name: '测试客户', age: version === 3 ? 20 : 21}]})
    }
    return reply({lead: {id: 10, customer_name: '测试客户', status: 'contacting'}, follow_ups: []})
  })
  await page.goto('/customers/10')
  await expect(page.getByText('年龄', {exact: true})).toHaveCount(1)
  await expect(page.getByText('语言能力', {exact: true})).toHaveCount(1)
  await expect(page.getByText('英语：雅思 6；日语：N2；德语：B1', {exact: true})).toBeVisible()
  await expect(page.getByText(/个大属性/)).toHaveCount(0)
  const input = page.getByLabel('当前研判输入')
  await expect(input).toContainText('"age": 20')
  await expect.poll(() => subscribed).toBe(true)
  version = 4
  releaseUpdate()
  await expect(input).toContainText('"age": 21')
})
