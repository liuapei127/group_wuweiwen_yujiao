import {expect,test} from '@playwright/test'

test('login page shows workspace branding (UI-only scope)',async({page})=>{
  await page.goto('/')
  await expect(page.getByRole('heading',{name:'登录你的工作空间'})).toBeVisible()
  await expect(page.getByLabel('员工手机号')).toBeVisible()
  await expect(page.getByLabel('登录密码')).toBeVisible()
  await expect(page.getByRole('button',{name:'登录工作台'})).toBeVisible()
})


test('visitor can sign in, reserve and cancel through the website', async ({page}) => {
  const event = {
    id: 1, event_name: '德国项目讲座', location: '报告厅',
    start_time: '2099-12-01T09:00:00', end_time: '2099-12-01T10:00:00', max_participants: 1,
  }
  let status: 'registered' | 'cancelled' | null = null
  await page.route('**/api/v1/visitors/login', route =>
    route.fulfill({json: {code: 0, data: {access_token: 'visitor-test', account_type: 'visitor'}}}))
  await page.route('**/api/v1/visitors/me', route =>
    route.fulfill({json: {code: 0, data: {account_type: 'visitor'}}}))
  const visitorProfile = {
    username: '13900009101', name: '测试游客', contact: '13900009101',
    account_type: 'visitor', created_at: '2026-11-15T07:00:00Z', avatar_url: null,
  }
  await page.route('**/api/v1/visitors/profile', route =>
    route.fulfill({json: {code: 0, data: visitorProfile}}))
  await page.route('**/api/v1/visitor/**', async route => {
    const {pathname} = new URL(route.request().url())
    const current = {...event, current_participants: status === 'registered' ? 1 : 0, reservation_status: status}
    const reply = (data: unknown) => route.fulfill({json: {code: 0, data}})
    if (pathname.endsWith('/reservation')) {
      status = route.request().method() === 'POST' ? 'registered' : 'cancelled'
      await reply({id: 4, status})
    } else if (pathname.endsWith('/reservations')) {
      await reply(status ? [{event: current, reservation: {id: 4, status}}] : [])
    } else if (pathname.endsWith('/events')) await reply([current])
    else await reply([])
  })
  await page.goto('/website/visitor/services')
  await expect(page).toHaveURL(/website$/)
  await expect(page.getByRole('dialog', {name: '官网登录'})).toBeVisible()
  await expect(page.getByRole('region', {name: '游客服务'})).toHaveCount(0)
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', {name: '官网登录'})).toBeHidden()
  await expect(page.getByLabel('手机号', {exact: true})).toBeHidden()
  const loginButton = page.getByRole('button', {name: /^登\s*录$/})
  await loginButton.click()
  const loginDialog = page.getByRole('dialog', {name: '官网登录'})
  await expect(loginDialog).toBeVisible()
  await expect(page).toHaveURL(/website$/)
  await page.keyboard.press('Escape')
  await expect(loginDialog).toBeHidden()
  await expect(loginButton).toBeFocused()
  await loginButton.click()
  await loginDialog.getByLabel('手机号', {exact: true}).fill('13900009101')
  await loginDialog.getByLabel('密码').fill('test-password')
  await loginDialog.getByRole('button', {name: /^登\s*录$/}).click()
  await expect(loginDialog).toBeHidden()
  await expect(page).toHaveURL(/website\/visitor$/)
  await expect(page.getByRole('region', {name: '游客服务'})).toHaveCount(0)
  await page.getByRole('button', {name: '查看活动和资料'}).click()
  await expect(page).toHaveURL(/website\/visitor\/services$/)
  const services = page.getByRole('region', {name: '游客服务'})
  await expect(services).toBeVisible()
  await expect(page.getByRole('button', {name: '修改密码', exact: true})).toHaveCount(0)
  await expect(page.getByRole('button', {name: '退出登录', exact: true})).toHaveCount(0)
  await page.getByRole('button', {name: /个人信息/}).click()
  const account = page.getByRole('dialog', {name: '个人信息'})
  await expect(account.getByText('测试游客', {exact: true})).toBeVisible()
  await expect(account.getByRole('button', {name: '更换头像'})).toHaveCount(0)
  await account.getByRole('button', {name: '编辑资料'}).click()
  await expect(account.getByRole('button', {name: '更换头像'})).toBeVisible()
  await account.getByRole('button', {name: '取消编辑'}).click()
  await expect(account.getByRole('button', {name: '更换头像'})).toHaveCount(0)
  await expect(account.getByRole('button', {name: '退出登录'})).toBeVisible()
  await account.getByRole('button', {name: '修改密码'}).click()
  const changePassword = page.getByRole('dialog', {name: '修改密码'})
  await expect(changePassword).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(changePassword).toBeHidden()
  await expect(page.getByRole('heading', {name: /粤教国际教育|活动与资料/})).toHaveCount(0)
  await expect(page.getByRole('navigation', {name: '官网导航'})).toHaveCount(0)
  await expect(page.getByRole('link', {name: /^(关于粤教|留学项目|留学生活)$/})).toHaveCount(0)
  await expect(services.getByRole('tablist')).toHaveAttribute('aria-orientation','vertical')
  await expect(services.getByRole('tab')).toHaveText([
    '服务指引', '活动预约', '我的预约', '材料提交', '课程与项目', '留学政策', '讲座视频',
  ])
  await page.getByRole('tab', {name: '讲座视频'}).press('Enter')
  await expect(page.getByText('讲座回看', {exact: true})).toBeVisible()
  await page.reload()
  await expect(services).toBeVisible()
  await page.getByRole('tab', {name: '活动预约'}).click()
  await page.getByRole('button', {name: /^预\s*约$/}).click()
  await page.getByRole('tab', {name: '我的预约'}).click()
  await expect(page.getByRole('tabpanel').getByText('已预约', {exact: true})).toBeVisible()
  await page.getByRole('tabpanel').getByRole('button', {name: '取消预约'}).click()
  await expect(page.getByRole('tabpanel').getByText('已取消', {exact: true})).toBeVisible()
  await page.getByRole('button', {name: '返回官网'}).click()
  await expect(page).toHaveURL(/website\/visitor$/)
  await expect(page.getByRole('heading', {name: /粤教国际教育/})).toBeVisible()
})


test('advisor can claim, record a call and screen a visitor', async ({page}) => {
  const stamp = '2026-11-13T04:00:00'
  const visitor = {visitor_id: 42, registered_at: stamp}
  const user = {
    id: 10, real_name: '顾问', role_name: '顾问',
    permissions: ['visitor-intake:read', 'visitor-intake:write', 'crm:read', 'crm:write'],
  }
  let claimed = false
  let leadId: number | null = null
  let lastContact: string | null = null
  let saved: {project: string; age: number; education: string} | null = null
  const assessment = {status: 'potential_match', missing_fields: [], findings: ['可以进入后续顾问核对']}
  const caseData = () => ({
    ...visitor, name: '访客甲', contact: '13700000000', claimed_at: stamp,
    last_contact_at: lastContact, manual_source_id: saved ? 100 : null, crm_lead_id: leadId,
  })
  await page.addInitScript(() => sessionStorage.setItem('ent-token', 'test-advisor'))
  await page.route('**/api/v1/**', async route => {
    const {pathname} = new URL(route.request().url())
    const method = route.request().method()
    const reply = (data: unknown) => route.fulfill({json: {code: 0, data}})
    if (pathname.endsWith('/auth/me')) return reply(user)
    if (pathname.endsWith('/pending')) return reply(claimed ? [] : [visitor])
    if (pathname.endsWith('/assigned')) return reply(claimed ? [caseData()] : [])
    if (pathname.endsWith('/visitor-intake/42')) return reply(caseData())
    if (pathname.endsWith('/claim')) {
      claimed = true
      return reply(caseData())
    }
    if (pathname.endsWith('/calls')) {
      const record = {id: 1, advisor_id: 10, notes: '已联系，确认年龄', recorded_at: stamp}
      if (method === 'POST') {
        expect(route.request().postDataJSON()).toEqual({request_id: expect.any(String), notes: record.notes})
        lastContact = stamp
        return reply(record)
      }
      return reply(lastContact ? [record] : [])
    }
    if (pathname.endsWith('/lead') && method === 'POST') {
      expect(route.request().postDataJSON()).toMatchObject({source_id: 100, customer_name: '访客甲', remark: '回访确认有意向'})
      leadId = 125
      return reply({id: leadId})
    }
    if (pathname.endsWith('/materials')) return reply([])
    if (pathname.endsWith('/reservations')) return reply([])
    if (pathname.endsWith('/screening')) {
      if (method === 'POST') {
        saved = route.request().postDataJSON()
        expect(saved).toMatchObject({project: 'sg_hospitality', age: 18, education: 'vocational_secondary'})
        return reply({source_id: 100, screening: assessment})
      }
      return reply({source_id: 100, raw_content: null, file_name: null, screening_input: saved, screening: assessment})
    }
    await reply({})
  })
  await page.goto('/visitor-intake')
  await expect(page.getByRole('heading', {name: '资源池'})).toBeVisible()
  await expect(page.getByText('13700000000')).toHaveCount(0)
  await page.getByRole('button', {name: '跟进该游客'}).click()
  await page.getByRole('button', {name: '确认跟进'}).click()
  await expect(page).toHaveURL(/\/customers$/)
  await page.goto('/visitor-intake')
  await page.getByRole('tab', {name: '我已认领'}).click()
  await page.getByRole('button', {name: '查看跟进'}).click()
  const detail = page.getByRole('dialog', {name: '访客甲 · 跟进记录'})
  await expect(detail.getByText('13700000000')).toBeVisible()
  await expect(detail.getByRole('button', {name: '保存并研判'})).toHaveCount(0)
  await detail.getByLabel('沟通内容').fill('已联系，确认年龄')
  await detail.getByRole('button', {name: '保存通话记录'}).click()
  await expect(detail.getByText('已联系，确认年龄')).toBeVisible()
  await detail.getByLabel('意向项目').click()
  await page.getByText('新加坡酒店就业班', {exact: true}).last().click()
  await detail.getByLabel('年龄').fill('18')
  await detail.getByLabel('学历类别').click()
  await page.getByText('中职或同等学历', {exact: true}).last().click()
  await detail.getByRole('button', {name: '保存并研判'}).click()
  await expect(detail.getByText('初筛符合', {exact: true})).toBeVisible()
  await expect(detail.getByLabel('年龄')).toHaveValue('18')
  await expect(detail.getByText('该历史记录尚未同步至客户管理')).toBeVisible()
})


test('website sends a student to student services after same-entry login', async ({page}) => {
  const reply = {json: {code: 0, data: {account_type: 'student'}}}
  await page.route('**/api/v1/visitors/login', route => route.fulfill({
    json: {code: 0, data: {account_type: 'student', access_token: 'website-test'}},
  }))
  await page.route('**/api/v1/visitors/me', route => route.fulfill(reply))
  await page.route('**/api/v1/visitors/profile', route => route.fulfill({json: {code: 0, data: {
    username: '13900009102', name: '测试学生', contact: '13900009102',
    account_type: 'student', created_at: '2026-11-15T07:00:00Z', avatar_url: null,
  }}}))
  await page.route('**/api/v1/student/**', route => {
    const path = new URL(route.request().url()).pathname
    const data = path.endsWith('/assistant/overview') ? {
      profile: {student_name: '测试学生', abroad_country: 'Germany'},
      applications: [], deadlines: [],
    } : path.endsWith('/policies') ? {
      country: 'Germany', resources: [{
        title: '德国职业培训签证', description: '职业培训申请入口', publisher: '德国联邦政府门户',
        url: 'https://www.make-it-in-germany.com/en/visa-recognition/visa-types/training',
      }],
    } : path.endsWith('/deadlines') ? {items: [{title: '论文提交', deadline: '2099-12-01T09:00:00'}], has_more: false}
      : path.endsWith('/profile') ? {abroad_country: 'Germany'} : path.endsWith('/application-progress') ? [{
      id: 7, target_school: '示例大学', target_major: '计算机', stage: 'submitted',
      progress_detail: '已提交材料', deadline: null, next_action: '等待审核',
    }] : []
    return route.fulfill({json: {code: 0, data}})
  })
  await page.route('**/api/v1/visitor/**', route => {
    const path = new URL(route.request().url()).pathname
    const data = path.endsWith('/materials') ? [{
      source_id: 1, file_name: '原报名材料.pdf', submitted_at: '2026-11-12T12:00:00', status: 'received',
    }] : path.endsWith('/reservations') ? [{
      event: {id: 11, event_name: '原预约讲座', start_time: '2099-12-01T09:00:00', location: '报告厅'},
      reservation: {id: 12, status: 'registered'},
    }] : []
    return route.fulfill({json: {code: 0, data}})
  })
  await page.goto('/website/visitor')
  await expect(page).toHaveURL(/website$/)
  await page.getByRole('button', {name: /^登\s*录$/}).click()
  const loginDialog = page.getByRole('dialog', {name: '官网登录'})
  await loginDialog.getByLabel('手机号', {exact: true}).fill('13900009102')
  await loginDialog.getByLabel('密码').fill('test-password')
  await loginDialog.getByRole('button', {name: /^登\s*录$/}).click()
  await expect(page).toHaveURL(/website\/student$/)
  await expect(page.getByRole('heading', {name: /欢迎回来，测试学生/})).toBeVisible()
  const studentNav = page.getByLabel('学生服务导航')
  await expect(studentNav.getByRole('button', {name: '投诉反馈'})).toBeVisible()
  await expect(page.getByText('留学方向 · 德国')).toBeVisible()
  await expect(page.getByRole('button', {name: /全部考务/})).toBeVisible()
  await studentNav.getByRole('button', {name: '申请进度'}).press('Enter')
  await expect(page.getByText('示例大学', {exact: true})).toBeVisible()
  await expect(page.getByText('等待审核', {exact: true})).toBeVisible()
  await studentNav.getByRole('button', {name: '留学政策'}).press('Enter')
  await expect(page.getByText('德国职业培训签证', {exact: true})).toBeVisible()
  await expect(page.getByRole('link', {name: '查看官方说明'})).toHaveAttribute('href', /make-it-in-germany/)
  await studentNav.getByRole('button', {name: '我的材料与活动'}).press('Enter')
  await page.getByRole('tab', {name: '我的预约'}).click()
  await expect(page.getByText('原预约讲座', {exact: true})).toBeVisible()
  await page.getByRole('tab', {name: '材料提交'}).click()
  await expect(page.getByText('原报名材料.pdf', {exact: true})).toBeVisible()
  await page.reload()
  await expect(page.getByRole('heading', {name: /欢迎回来，测试学生/})).toBeVisible()
})

for (const {role, permission, expected} of [
  {role: 'employee', permission: 'crm:read', expected: '/customers'},
  {role: 'team_leader', permission: 'leaves:read', expected: '/leaves'},
  {role: 'manager', permission: 'tickets:read', expected: '/tickets'},
  {role: 'admin', permission: 'website-accounts:manage', expected: '/settings/website-accounts'},
]) {
  test(role + ' enters the work page for their role', async ({page}) => {
    const user = {id: 10, real_name: '员工', role_code: role, role_name: role,
                  permissions: [permission, 'dashboard:read']}
    await page.addInitScript(() => sessionStorage.setItem('ent-token', 'employee-token'))
    await page.route('**/api/v1/**', route => route.fulfill({json: {
      code: 0, data: new URL(route.request().url()).pathname.endsWith('/auth/me') ? user : [],
    }}))
    await page.goto('/')
    await expect(page).toHaveURL(expected)
  })
}


test('website account operator can create a student record from a visitor', async ({page}) => {
  const user = {id: 10, real_name: '管理员', role_code: 'admin', role_name: '管理员',
    permissions: ['website-accounts:manage']}
  const account = {id: 2, username: 'visitor-a', name: '新学生', contact: '联系信息',
    student_id: null, student_enabled: false}
  let saved = false
  await page.addInitScript(() => sessionStorage.setItem('ent-token', 'employee-test'))
  await page.route('**/api/v1/**', route => {
    const path = new URL(route.request().url()).pathname
    const reply = (data: unknown) => route.fulfill({json: {code: 0, data}})
    if (path.endsWith('/auth/me')) return reply(user)
    if (path.endsWith('/enrollment-projects')) return reply([{id: 1, project_name: '德国预科项目'}])
    if (path.endsWith('/enrollment-projects/1/classes')) return reply([{id: 10, name: '2026秋季一班', teacher_id: 30, teacher_name: '班主任甲'}])
    if (path.endsWith('/student-access') && route.request().method() === 'POST') {
      expect(route.request().postDataJSON()).toEqual({project_id: 1, class_id: 10})
      saved = true
      return reply({...account, student_id: 8, student_enabled: true})
    }
    if (path.endsWith('/website-accounts')) {
      return reply([saved ? {...account, student_id: 8, student_enabled: true} : account])
    }
    return reply([])
  })
  await page.goto('/settings/website-accounts')
  await page.getByRole('button', {name: '开通学生身份'}).click()
  const dialog = page.getByRole('dialog', {name: '开通学生身份'})
  await dialog.getByRole('button', {name: '新建学生档案'}).click()
  await dialog.getByLabel('项目').click()
  await page.getByText('德国预科项目', {exact: true}).last().click()
  await dialog.getByLabel('班级').click()
  await page.getByText('2026秋季一班', {exact: true}).last().click()
  await dialog.getByRole('button', {name: /^确\s*定$/}).click()
  await expect(page.getByText('学生已开通', {exact: true})).toBeVisible()
})


test('student assistant keeps the chosen conversation and draft after an older reply', async ({page}) => {
  const conversations = [{id: 'old', title: '原来的对话'}, {id: 'new', title: '新对话'}]
  const originalTurns = Array.from({length: 24}, (_, index) => ({
    id: index + 1, role: index % 2 === 0 ? 'user' : 'assistant', content: '历史消息 ' + index,
  }))
  let finishReply!: () => void
  const delayedReply = new Promise<void>(resolve => {finishReply = resolve})

  await page.route('**/api/v1/visitors/login', route => route.fulfill({
    json: {code: 0, data: {account_type: 'student', access_token: 'website-test'}},
  }))
  await page.route('**/api/v1/visitors/me', route => route.fulfill({json: {code: 0, data: {account_type: 'student'}}}))
  await page.route('**/api/v1/visitors/profile', route => route.fulfill({json: {code: 0, data: {
    username: '13900009102', name: '测试学生', contact: '13900009102', account_type: 'student', created_at: '2026-11-15T07:00:00Z', avatar_url: null,
  }}}))
  await page.route('**/api/v1/student/**', async route => {
    const path = new URL(route.request().url()).pathname
    const method = route.request().method()
    let data: unknown = []
    if (path.endsWith('/assistant/overview')) {
      data = {profile: {student_name: '测试学生', abroad_country: 'Germany'}, applications: [], deadlines: []}
    } else if (path.endsWith('/assistant/conversations')) {
      data = conversations
    } else if (path.includes('/assistant/conversations/')) {
      const id = path.split('/').pop()
      data = {id, title: '', messages: id === 'old' ? originalTurns : []}
    } else if (path.endsWith('/assistant') && method === 'POST') {
      await delayedReply
      originalTurns.push({id: 25, role: 'user', content: '发给旧对话'}, {id: 26, role: 'assistant', content: '旧对话收到的新回复'})
      data = {answer: '旧对话收到的新回复', conversation_id: 'old'}
    } else if (path.endsWith('/profile')) {
      data = {abroad_country: 'Germany'}
    } else if (path.endsWith('/deadlines')) {
      data = {items: []}
    }
    await route.fulfill({json: {code: 0, data}})
  })

  await page.goto('/website')
  await page.getByRole('button', {name: /^登\s*录$/}).click()
  const login = page.getByRole('dialog', {name: '官网登录'})
  await login.getByLabel('手机号', {exact: true}).fill('13900009102')
  await login.getByLabel('密码').fill('test-password')
  await login.getByRole('button', {name: /^登\s*录$/}).click()
  await expect(page).toHaveURL(/website\/student$/)
  const studentNav = page.getByLabel('学生服务导航')
  await studentNav.getByRole('button', {name: '学生助手'}).click()
  await page.getByRole('button', {name: '对话记录'}).click()
  const history = page.getByRole('dialog', {name: '对话记录'})
  await history.getByRole('button', {name: '原来的对话'}).click()
  const input = page.getByRole('textbox', {name: '输入要办的事'})
  await input.fill('发给旧对话')
  await input.press('Enter')
  await expect(page.getByText('正在了解你的问题…')).toBeVisible()
  await page.getByRole('button', {name: '对话记录'}).click()
  await history.getByRole('button', {name: '新对话', exact: true}).click()
  await input.fill('新会话里的草稿')
  const scrollBeforeReply = await page.evaluate(() => window.scrollY)
  const reply = page.waitForResponse(response => response.url().endsWith('/api/v1/student/assistant'))
  finishReply()
  await reply
  await expect(page.getByRole('button', {name: /^发\s*送$/})).toBeEnabled()
  await expect(input).toHaveValue('新会话里的草稿')
  expect(await page.evaluate(() => window.scrollY)).toBe(scrollBeforeReply)
  await page.getByRole('button', {name: '对话记录'}).click()
  await history.getByRole('button', {name: '原来的对话'}).click()
  await expect(page.getByText('旧对话收到的新回复')).toBeVisible()
  await page.getByRole('button', {name: '对话记录'}).click()
  await history.getByRole('button', {name: '新对话', exact: true}).click()
  await expect(input).toHaveValue('新会话里的草稿')
  await studentNav.getByRole('button', {name: '申请进度'}).click()
  await studentNav.getByRole('button', {name: '学生助手'}).click()
  await expect(input).toHaveValue('新会话里的草稿')
})

test.describe('todo status form initialization', () => {
  test.use({serviceWorkers:'block'})
  test('shows the current status on first open and when changing tasks', async ({page}) => {
    const tasks = [
      {id:71,title:'待处理任务',status:'pending',priority:'medium',todo_type:'custom'},
      {id:72,title:'进行中任务',status:'in_progress',priority:'medium',todo_type:'custom'},
    ]
    let updated:unknown
    await page.addInitScript(()=>sessionStorage.setItem('ent-token','test-todo-owner'))
    await page.route('**/api/v1/**', async route => {
      const path=new URL(route.request().url()).pathname
      const reply=(data:unknown)=>route.fulfill({json:{code:0,data}})
      if(path==='/api/v1/auth/me')return reply({id:10,real_name:'待办测试员工',role_code:'employee',role_name:'员工',
        permissions:['todos:read','todos:write'],student_ids:[]})
      if(path==='/api/v1/enterprise/todos')return reply(tasks)
      if(path==='/api/v1/enterprise/todos/72'&&route.request().method()==='PATCH') {
        updated=route.request().postDataJSON()
        tasks[1].status='done'
        return reply(tasks[1])
      }
      return reply({})
    })
    await page.goto('/todos')
    await page.getByRole('row').filter({hasText:'待处理任务'}).getByRole('button',{name:'处理',exact:true}).click()
    const dialog=page.getByRole('dialog',{name:'更新待办状态'})
    await expect(dialog.getByLabel('当前状态')).toBeDisabled()
    await expect(dialog.locator('.ant-form-item').filter({hasText:'当前状态'})).toContainText('待处理')
    await expect(dialog.locator('.ant-form-item').filter({hasText:'目标状态'})).toContainText('已完成')
    await dialog.getByRole('button',{name:/^取\s*消$/}).click()
    await expect(dialog).toBeHidden()
    await page.getByRole('row').filter({hasText:'进行中任务'}).getByRole('button',{name:'处理',exact:true}).click()
    await expect(dialog.locator('.ant-form-item').filter({hasText:'当前状态'})).toContainText('进行中')
    await expect(dialog.locator('.ant-form-item').filter({hasText:'目标状态'})).toContainText('已完成')
    await dialog.getByRole('button',{name:'确认提交'}).click()
    await expect(dialog).toBeHidden()
    expect(updated).toEqual({expected_status:'in_progress',status:'done'})
    await expect(page.getByRole('row').filter({hasText:'进行中任务'})).toContainText('已完成')
    await page.getByRole('button',{name:/新增待办/}).click()
    const create=page.getByRole('dialog',{name:'新增待办'})
    await expect(create.getByLabel('待办标题')).toHaveValue('')
    await expect(create.locator('.ant-form-item').filter({hasText:'优先级'})).toContainText('普通')
  })
})


test.describe('report center review changes', () => {
  test.use({serviceWorkers:'block'})
  test('merges customer charts and separates report generation from PDF download', async ({page}) => {
    let generated=0, pdfRequests=0, intelligenceRequests=0
    let lastMetric=''
    await page.addInitScript(()=>sessionStorage.setItem('ent-token','report-review'))
    await page.route('**/api/v1/**',async route=>{
      const url=new URL(route.request().url()), path=url.pathname
      const reply=(data:unknown)=>route.fulfill({json:{code:0,data}})
      if(path.endsWith('/auth/me'))return reply({id:10,real_name:'报表主管',role_code:'manager',role_name:'主管',permissions:['reports:operations:read','reports:summary:read'],student_ids:[]})
      if(path.endsWith('/customers/intelligence')){intelligenceRequests++;return reply({})}
      if(path.endsWith('/customers/analysis'))return reply({comparisons:{previous:{start:'2026-10-01',end:'2026-10-17',count:4,change:1,percent:25}},groups:{
        intended_country:[{label:'德国',count:5,signed:2,signed_percent:40}],education_level:[{label:'本科',count:5,signed:2,signed_percent:40}],
        intended_project:[{label:'预科',count:5,signed:2,signed_percent:40}],source_channel:[{label:'官网',count:5,signed:2,signed_percent:40}]}})
      if(path.endsWith('/customers/archive')){generated++;return reply({archive_id:901})}
      if(path.endsWith('/archive/901/pdf')){pdfRequests++;return route.fulfill({contentType:'application/pdf',body:'%PDF-1.4\n%%EOF'})}
      if(path.endsWith('/board/customers')){
        lastMetric=url.searchParams.get('metric')||''
        return reply({department:'A',leads_by_status:{new:3,signed:2},transitions:{signed:7,lost:1},lost_reasons:{预算:1},follow_ups:{phone:3},
          departments:[{department:'A',new:5,signed:7,lost:1}],status_history_since:'2026-01-01',
          items:lastMetric?[{id:7,customer_name:'分组客户',status:'new',intended_country:'德国',education_level:'本科',intended_project:'预科'}]:[],has_more:false})
      }
      return reply([])
    })
    await page.goto('/reporting')
    const panel=page.locator('#report-panel-customers')
    await expect(panel.getByRole('region',{name:'来源渠道分析',exact:true})).toHaveCount(1)
    await expect(panel.getByText('客户特征聚类与风险提示',{exact:true})).toHaveCount(0)
    await expect(panel.getByText('已记录的转化路径',{exact:true})).toHaveCount(0)
    await expect(panel.getByText('获客渠道分析',{exact:true})).toHaveCount(0)
    await expect(panel.locator('[data-chart=donut]')).toHaveCount(1)
    await expect(panel.locator('[data-chart=grouped]')).toHaveCount(1)
    const metrics=await panel.locator('.report-center-grid').boundingBox()
    const charts=await panel.getByRole('region',{name:'新增线索当前状态',exact:true}).boundingBox()
    expect(metrics!.y).toBeLessThan(charts!.y)
    await panel.getByRole('button',{name:'意向国家 · 德国 · 5 条明细',exact:true}).click()
    await expect(page.getByRole('dialog').getByText('分组客户',{exact:true})).toBeVisible()
    expect(lastMetric).toBe('country')
    await page.keyboard.press('Escape')
    await expect(page.getByRole('dialog')).toBeHidden()
    await expect(panel.getByRole('button',{name:'下载 PDF',exact:true})).toBeDisabled()
    await panel.getByRole('button',{name:'生成报告',exact:true}).click()
    await expect(panel.getByRole('button',{name:'下载 PDF',exact:true})).toBeEnabled()
    expect(generated).toBe(1);expect(pdfRequests).toBe(0);expect(intelligenceRequests).toBe(0)
    const download=page.waitForEvent('download')
    await panel.getByRole('button',{name:'下载 PDF',exact:true}).click()
    expect((await download).suggestedFilename()).toContain('901.pdf')
    expect(pdfRequests).toBe(1);expect(generated).toBe(1)
    await panel.getByLabel('开始日期').fill('2026-10-01')
    await expect(panel.getByRole('button',{name:/下载 PDF$/})).toBeDisabled()
    await page.emulateMedia({media:'print'})
    await expect(panel.locator('.report-filter-panel')).toBeHidden()
    await expect(panel.getByRole('region',{name:'部门经营对比'})).toBeVisible()
    await expect(page.locator('.report-center > section:visible')).toHaveCount(1)
  })

  test('uses complaint donut and ordered columns and hides unconfigured timing panels',async({page})=>{
    await page.addInitScript(()=>sessionStorage.setItem('ent-token','report-review'))
    await page.route('**/api/v1/**',async route=>{
      const url=new URL(route.request().url()),path=url.pathname
      const reply=(data:unknown)=>route.fulfill({json:{code:0,data}})
      if(path.endsWith('/auth/me'))return reply({id:10,real_name:'报表主管',role_code:'manager',role_name:'主管',permissions:['reports:operations:read','reports:summary:read'],student_ids:[]})
      if(path.endsWith('/complaints/analysis'))return reply({first_response:{samples:0,average_hours:null},resolution:{samples:0,average_hours:null},overdue_days:null})
      if(path.endsWith('/complaints/archive'))return route.fulfill({status:503,json:{detail:'报告生成失败，请重试'}})
      if(path.endsWith('/board/complaints'))return reply({department:'A',complaints_by_status:{pending:2,processing:1,resolved:2},
        categories:{服务:5},satisfaction:{'5':2,'3':1},backlog:{'14 天以上':2,'0–2 天':1,'7–13 天':0,'3–6 天':0},items:[],has_more:false})
      if(path.endsWith('/board/employees'))return reply({expected:2,submitted:0,missing:2,departments:[{department:'A',expected:2,submitted:0,missing:2}],
        items:[{employee_id:71,name:'同名员工',department:'A',report_days:0},{employee_id:72,name:'同名员工',department:'B',report_days:0}],has_more:false})
      if(path.endsWith('/projects/health'))return reply({items:[{project_id:1,project_name:'预科项目',students:2,open_complaints:0,overdue_applications:0,overdue_deadlines:0,score:100}],note:'按当前班级统计'})
      return reply([])
    })
    await page.goto('/reporting')
    await page.getByRole('button',{name:'投诉周报',exact:true}).click()
    const panel=page.locator('#report-panel-complaints')
    await expect(panel.getByRole('region',{name:'投诉状态',exact:true})).toHaveAttribute('data-chart','donut')
    const backlog=panel.getByRole('region',{name:'积压账龄',exact:true})
    await expect(backlog).toHaveAttribute('data-chart','columns')
    await expect(backlog.locator('.report-column-label')).toHaveText(['0–2 天','3–6 天','7–13 天','14 天以上'])
    await expect(panel.getByRole('region',{name:'满意度分布',exact:true}).locator('.report-column-label')).toHaveText(['3 分','5 分'])
    await expect(panel.getByText('投诉处理时效',{exact:true})).toHaveCount(0)
    await expect(panel.getByText(/暂无样本|尚未配置|尚未设置投诉超时标准/)).toHaveCount(0)
    await panel.getByRole('button',{name:'生成报告',exact:true}).click()
    await expect(panel.getByText('报告生成失败，请重试',{exact:true})).toBeVisible()
    await expect(panel.getByRole('button',{name:'下载 PDF',exact:true})).toBeDisabled()
    await page.getByRole('button',{name:'员工日报周报',exact:true}).click()
    const employees=page.locator('#report-panel-employees')
    await expect(employees.getByRole('columnheader',{name:'员工编号',exact:true})).toBeVisible()
    await expect(employees.getByRole('cell',{name:'同名员工',exact:true})).toHaveCount(2)
    const metrics=await employees.locator('.report-center-grid').boundingBox()
    const health=await employees.getByText('跨项目服务健康度',{exact:true}).boundingBox()
    expect(metrics!.y).toBeLessThan(health!.y)
  })
})
