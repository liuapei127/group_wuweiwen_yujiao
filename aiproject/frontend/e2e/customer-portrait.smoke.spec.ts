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

test('registered customer chat survives refresh and page changes with recent context', async ({page}) => {
  const requests: {query: string; history: {role: string; content: string}[]; session_id?: string; start_session?: boolean}[] = []
  let expired = false
  await page.addInitScript(() => sessionStorage.setItem('yujiao-visitor-token', 'member-token'))
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    const data = path.endsWith('/me') ? {account_type: 'visitor'} : path.endsWith('/profile') ? {
      account_type: 'visitor', name: '测试客户', username: '13900000001', created_at: '2026-11-17T16:00:00Z',
    } : []
    return route.fulfill({json: {code: 0, data}})
  })
  await page.route('**/api/cs/visitor/chat', route => {
    const turn = route.request().postDataJSON()
    requests.push(turn)
    if (turn.session_id && !expired) {
      expired = true
      return route.fulfill({status: 404, json: {detail: '客服会话已失效'}})
    }
    return route.fulfill({json: {code: 0, data: {answer: '本次先聊住宿安排', session_id: 'b'.repeat(64)}}})
  })
  await page.goto('/website/visitor')
  const open = page.getByRole('button', {name: '打开粤教升学助手'})
  const input = page.getByRole('textbox', {name: '输入想了解的问题'})
  await open.click()
  await input.fill('这轮先聊住宿')
  await input.press('Enter')
  await expect(page.getByText('本次先聊住宿安排', {exact: true})).toBeVisible()
  await page.reload()
  await open.click()
  await expect(page.getByText('这轮先聊住宿', {exact: true})).toBeVisible()
  await input.fill('接着刚才说')
  await input.press('Enter')
  await expect.poll(() => requests.length).toBe(3)
  expect(requests[1].history).toEqual([
    {role: 'user', content: '这轮先聊住宿'}, {role: 'assistant', content: '本次先聊住宿安排'},
  ])
  expect(requests[2].history).toEqual(requests[1].history)
  expect(requests[2].start_session).toBe(true)
  await page.getByRole('button', {name: '关闭客服'}).click()
  await page.getByRole('button', {name: '查看活动和资料', exact: true}).click()
  await open.click()
  await expect(page.getByText('这轮先聊住宿', {exact: true})).toBeVisible()
  await page.getByRole('button', {name: '清空对话'}).click()
  await expect(page.getByText('这轮先聊住宿', {exact: true})).toHaveCount(0)
  await input.fill('换一个话题')
  await input.press('Enter')
  await expect.poll(() => requests.length).toBe(4)
  expect(requests[3].history).toEqual([])
  expect(requests[3].session_id).toBeUndefined()
})

test('registered customer logout isolates a new account and ignores an older pending reply', async ({page}) => {
  let releaseReply!: () => void
  const pending = new Promise<void>(resolve => {releaseReply = resolve})
  let started = false
  let newHistory: unknown
  await page.addInitScript(() => sessionStorage.setItem('yujiao-visitor-token', 'member-a'))
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    const data = path.endsWith('/login') ? {account_type: 'visitor', access_token: 'member-b'}
      : path.endsWith('/me') ? {account_type: 'visitor'} : path.endsWith('/profile') ? {
        account_type: 'visitor', name: '测试客户', username: '13900000001', created_at: '2026-11-17T16:00:00Z',
      } : []
    return route.fulfill({json: {code: 0, data}})
  })
  await page.route('**/api/cs/visitor/chat', async route => {
    if (route.request().headers().authorization === 'Bearer member-a') {
      started = true
      await pending
      return route.fulfill({json: {code: 0, data: {answer: '前一个账号的迟到回复', session_id: 'a'.repeat(64)}}})
    }
    newHistory = route.request().postDataJSON().history
    return route.fulfill({json: {code: 0, data: {answer: '新账号回复', session_id: 'b'.repeat(64)}}})
  })
  await page.goto('/website/visitor')
  await page.getByRole('button', {name: '打开粤教升学助手'}).click()
  await page.getByRole('textbox', {name: '输入想了解的问题'}).fill('前一个账号的临时问题')
  await page.getByRole('button', {name: '发送', exact: true}).click()
  await expect.poll(() => started).toBe(true)
  const oldKey = await page.evaluate(() => sessionStorage.getItem('website-customer-chat-session'))
  await page.getByRole('button', {name: '关闭客服'}).click()
  await page.getByRole('button', {name: /个人信息/}).click()
  await page.getByRole('dialog', {name: '个人信息'}).getByRole('button', {name: '退出登录', exact: true}).click()
  await expect(page).toHaveURL(/website$/)
  await page.getByRole('button', {name: /^登\s*录$/}).click()
  const login = page.getByRole('dialog', {name: '官网登录'})
  await login.getByLabel('手机号', {exact: true}).fill('13900000002')
  await login.getByLabel('密码', {exact: true}).fill('Test!9876')
  await login.getByRole('button', {name: /^登\s*录$/}).click()
  await expect(page).toHaveURL(/website\/visitor$/)
  const completed = page.waitForResponse(response => response.url().endsWith('/api/cs/visitor/chat'))
  releaseReply()
  await completed
  await page.getByRole('button', {name: '打开粤教升学助手'}).click()
  await expect(page.getByText('前一个账号的迟到回复', {exact: true})).toHaveCount(0)
  await expect(page.getByText('前一个账号的临时问题', {exact: true})).toHaveCount(0)
  expect(await page.evaluate(key => sessionStorage.getItem(key!), oldKey)).toBeNull()
  await page.getByRole('textbox', {name: '输入想了解的问题'}).fill('新账号提问')
  await page.getByRole('button', {name: '发送', exact: true}).click()
  await expect(page.getByText('新账号回复', {exact: true})).toBeVisible()
  expect(newHistory).toEqual([])
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

for (const uploader of ['visitor', 'employee']) {
  test(`${uploader} confirms ownership before importing a document without identity`, async ({page}) => {
    const visitor = uploader === 'visitor'
    const confirmation = visitor ? '我确认该资料属于本人' : '我确认该资料属于当前客户'
    const endpoint = visitor ? '/api/v1/visitors/customer-profile' : '/api/v1/consultant/leads/10'
    let confirmed = false
    let previews = 0
    await page.addInitScript(visitor ? () => sessionStorage.setItem('yujiao-visitor-token', 'import-ui-test')
      : () => sessionStorage.setItem('ent-token', 'import-ui-test'))
    await page.route('**/api/v1/**', async route => {
      const url = new URL(route.request().url())
      const reply = (data: unknown) => route.fulfill({json: {code: 0, data}})
      if (url.pathname.endsWith('/auth/me')) return reply({
        id: 10, real_name: '测试顾问', role_code: 'advisor', role_name: '顾问',
        permissions: ['crm:read', 'crm:write'], student_ids: [],
      })
      if (url.pathname === '/api/v1/visitors/me') return reply({account_type: 'visitor'})
      if (url.pathname === '/api/v1/visitors/profile') return reply({
        account_type: 'visitor', name: '测试客户', username: '13900000001', created_at: '2026-11-17T16:00:00Z',
      })
      if (url.pathname === endpoint + '/imports/preview') {
        previews++
        return reply({preview_id: 'import-preview', version: 0, file_name: '语言证书.txt', matches: [],
          ownership_confirmation_required: true, ownership_confirmation_text: confirmation, customer_name: '测试客户',
          fields: [{field: 'age', current: null, proposed: 22}]})
      }
      if (url.pathname === endpoint + '/imports/confirm') {
        expect(route.request().postDataJSON()).toMatchObject({ownership_confirmed: true, fields: ['age']})
        confirmed = true
        return reply({version: 1, age: 22})
      }
      if (url.pathname === endpoint || url.pathname === endpoint + '/profile') {
        if (url.searchParams.has('watch_version')) {
          return route.fulfill({contentType: 'text/event-stream', body: 'event: result\ndata: {"data":{"changed":false}}\n\n'})
        }
        return reply({customer_name: '测试客户', version: confirmed ? 1 : 0, age: confirmed ? 22 : null,
          readiness: {ready: false, missing_fields: []}, screening_input: [{id: 'U_010'}]})
      }
      return reply({lead: {id: 10, customer_name: '测试客户', status: 'contacting'}, follow_ups: []})
    })
    await page.goto(visitor ? '/website/profile' : '/customers/10')
    if (visitor) {
      await expect(page.getByText('客户资料', {exact: true})).toBeVisible()
      await expect(page.getByText('用户画像与研判输入', {exact: true})).toHaveCount(0)
    }
    const upload = () => page.getByLabel('选择客户资料').setInputFiles({
      name: '语言证书.txt', mimeType: 'text/plain', buffer: Buffer.from('年龄：22'),
    })
    await upload()
    const dialog = page.getByRole('dialog', {name: '确认导入客户资料'})
    const save = dialog.getByRole('button', {name: '确认保存'})
    await expect(save).toBeDisabled()
    await dialog.getByRole('checkbox', {name: confirmation, exact: true}).check()
    await expect(save).toBeEnabled()
    await save.click()
    await expect(dialog).toBeHidden()
    expect(confirmed).toBe(true)
    await upload()
    await expect(dialog).toBeVisible()
    await expect(save).toBeDisabled()
    await expect(dialog.getByRole('checkbox', {name: confirmation, exact: true})).not.toBeChecked()
    expect(previews).toBe(2)
  })
}

for (const reader of ['visitor', 'employee']) {
  test(`${reader} can preview and download imported files and read text materials`, async ({page}) => {
    const visitor = reader === 'visitor'
    const token = 'import-preview-test'
    const endpoint = visitor ? '/api/v1/visitors/customer-profile' : '/api/v1/consultant/leads/10'
    const pdf = Buffer.from('JVBERi0xLjMKJeLjz9MKMSAwIG9iago8PAovUHJvZHVjZXIgKHB5cGRmKQo+PgplbmRvYmoKMiAwIG9iago8PAovVHlwZSAvUGFnZXMKL0NvdW50IDEKL0tpZHMgWyA0IDAgUiBdCj4+CmVuZG9iagozIDAgb2JqCjw8Ci9UeXBlIC9DYXRhbG9nCi9QYWdlcyAyIDAgUgo+PgplbmRvYmoKNCAwIG9iago8PAovVHlwZSAvUGFnZQovUmVzb3VyY2VzIDw8Cj4+Ci9NZWRpYUJveCBbIDAuMCAwLjAgMjAwIDEwMCBdCi9QYXJlbnQgMiAwIFIKPj4KZW5kb2JqCnhyZWYKMCA1CjAwMDAwMDAwMDAgNjU1MzUgZiAKMDAwMDAwMDAxNSAwMDAwMCBuIAowMDAwMDAwMDU0IDAwMDAwIG4gCjAwMDAwMDAxMTMgMDAwMDAgbiAKMDAwMDAwMDE2MiAwMDAwMCBuIAp0cmFpbGVyCjw8Ci9TaXplIDUKL1Jvb3QgMyAwIFIKL0luZm8gMSAwIFIKPj4Kc3RhcnR4cmVmCjI1NgolJUVPRgo=', 'base64')
    const imports = [
      {id: 21, file_name: '测试资料.pdf', create_time: '2026-11-18T01:00:00'},
      {id: 20, file_name: null, create_time: '2026-11-17T01:00:00'},
    ]
    await page.addInitScript(({visitor, token}) => sessionStorage.setItem(visitor ? 'yujiao-visitor-token' : 'ent-token', token), {visitor, token})
    await page.route('**/api/v1/**', async route => {
      const url = new URL(route.request().url())
      const reply = (data: unknown) => route.fulfill({json: {code: 0, data}})
      if (url.pathname.endsWith('/auth/me')) return reply({id: 10, real_name: '测试顾问', role_code: 'advisor',
        role_name: '顾问', permissions: ['crm:read'], student_ids: []})
      if (url.pathname === '/api/v1/visitors/me') return reply({account_type: 'visitor'})
      if (url.pathname === '/api/v1/visitors/profile') return reply({account_type: 'visitor', name: '测试客户',
        username: '13900000001', created_at: '2026-11-17T16:00:00Z'})
      if (url.pathname === endpoint + '/imports/21') return reply({source_id: 21, file_name: '测试资料.pdf',
        raw_content: 'PDF 已保存正文', has_attachment: true})
      if (url.pathname === endpoint + '/imports/20') return reply({source_id: 20, file_name: null,
        raw_content: '历史文字资料正文', has_attachment: false})
      if (url.pathname === endpoint + '/imports/21/attachment') {
        expect(route.request().headers().authorization).toBe('Bearer ' + token)
        return route.fulfill({contentType: 'application/pdf', body: pdf})
      }
      if (url.pathname === endpoint || url.pathname === endpoint + '/profile') {
        if (url.searchParams.has('watch_version')) return route.fulfill({contentType: 'text/event-stream',
          body: 'event: result\ndata: {"data":{"changed":false}}\n\n'})
        return reply({customer_name: '测试客户', version: 0, imports, readiness: {ready: false, missing_fields: []}})
      }
      return reply({lead: {id: 10, customer_name: '测试客户', status: 'contacting'}, follow_ups: []})
    })
    await page.goto(visitor ? '/website/profile' : '/customers/10')
    await page.getByRole('button', {name: '测试资料.pdf', exact: true}).click()
    const pdfDialog = page.getByRole('dialog', {name: '测试资料.pdf', exact: true})
    await expect(pdfDialog.getByText('PDF 已保存正文', {exact: true})).toBeVisible()
    await expect(pdfDialog.locator('iframe[title="资料原件"]')).toHaveAttribute('src', /^blob:/)
    const [download] = await Promise.all([
      page.waitForEvent('download'), pdfDialog.getByRole('link', {name: '下载原件', exact: true}).click(),
    ])
    expect(download.suggestedFilename()).toBe('测试资料.pdf')
    const stream = await download.createReadStream()
    const chunks: Buffer[] = []
    for await (const chunk of stream!) chunks.push(Buffer.from(chunk))
    expect(Buffer.concat(chunks).equals(pdf)).toBe(true)
    await pdfDialog.getByRole('button', {name: '关闭', exact: true}).click()
    await page.getByRole('button', {name: '文字资料', exact: true}).click()
    const textDialog = page.getByRole('dialog', {name: '文字资料', exact: true})
    await expect(textDialog.getByText('历史文字资料正文', {exact: true})).toBeVisible()
    await expect(textDialog.locator('iframe')).toHaveCount(0)
    await expect(textDialog.getByRole('link', {name: '下载原件'})).toHaveCount(0)
  })
}
