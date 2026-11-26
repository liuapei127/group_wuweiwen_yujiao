import {expect, test} from '@playwright/test'

test.use({serviceWorkers: 'block'})

test('teacher reviews a leave and can find the resulting processed record', async ({page}) => {
  let status = 'pending'
  let comment = ''
  const leave = () => ({id: 15, student_id: 21, student_name: '审批测试学生', leave_type: 'sick',
    start_time: '2026-12-10T09:00:00', end_time: '2026-12-10T11:00:00', reason: '复查', status,
    approval_comment: comment, approver_id: 30})
  await page.addInitScript(() => sessionStorage.setItem('ent-token', 'closure-test'))
  await page.route('**/api/v1/**', route => {
    const url = new URL(route.request().url())
    const reply = (data: unknown) => route.fulfill({json: {code: 0, data}})
    if (url.pathname.endsWith('/auth/me')) return reply({id: 30, real_name: '班主任', role_code: 'team_leader', role_name: '班主任',
      permissions: ['leaves:read', 'leaves:approve'], student_ids: [21]})
    if (url.pathname.endsWith('/leaves/15/approve')) {
      const body = route.request().postDataJSON()
      expect(body.decision).toBe('rejected')
      expect(body).not.toHaveProperty('approver_id')
      expect(body.approval_comment).toBe('请补充复查时间')
      status = 'rejected'; comment = body.approval_comment
      return reply(leave())
    }
    if (url.pathname.endsWith('/leaves')) return reply(!url.searchParams.get('status') || url.searchParams.get('status') === status ? [leave()] : [])
    return reply([])
  })
  await page.goto('/leaves')
  await page.getByRole('button', {name: '拒绝', exact: true}).click()
  const modal = page.getByRole('dialog', {name: '核对后拒绝请假'})
  await expect(modal).toContainText('审批测试学生')
  await expect(modal).toContainText('复查')
  await modal.getByRole('button', {name: '确认提交'}).click()
  await expect(modal.getByRole('alert')).toContainText('请填写审批意见')
  await modal.getByLabel('审批意见').fill('请补充复查时间')
  await modal.getByRole('button', {name: '确认提交'}).click()
  await expect(modal).toBeHidden()
  await page.getByRole('combobox', {name: '请假状态'}).click()
  await page.getByTitle('已拒绝', {exact: true}).click()
  await expect(page.getByRole('row').filter({hasText: '审批测试学生'})).toContainText('请补充复查时间')
  await expect(page.getByRole('button', {name: '同意', exact: true})).toHaveCount(0)
  await expect(page.getByRole('button', {name: '拒绝', exact: true})).toHaveCount(0)
})

test('manager can act only on assigned tickets and source todos have no completion shortcut', async ({page}) => {
  let processing = false
  await page.addInitScript(() => sessionStorage.setItem('ent-token', 'manager-closure'))
  await page.route('**/api/v1/**', route => {
    const url = new URL(route.request().url())
    const reply = (data: unknown) => route.fulfill({json: {code: 0, data}})
    if (url.pathname.endsWith('/auth/me')) return reply({id: 11, real_name: '主管', role_code: 'manager', role_name: '主管',
      permissions: ['tickets:read', 'tickets:write', 'todos:read', 'todos:write', 'leaves:read'], student_ids: []})
    if (url.pathname.endsWith('/tickets/1') && route.request().method() === 'PATCH') {
      expect(route.request().postDataJSON()).toMatchObject({expected_status: 'pending', status: 'processing'})
      processing = true
      return reply({id: 1, status: 'processing'})
    }
    if (url.pathname.endsWith('/tickets')) return reply([
      {id: 1, student_id: 21, student_name: '学生一', category: 'company', content: '主管核实服务', status: processing ? 'processing' : 'pending', assignee_id: 11, can_process: true},
      {id: 2, student_id: 22, student_name: '学生二', category: 'learning', status: 'pending', assignee_id: 30, can_process: false},
    ])
    if (url.pathname.endsWith('/todos')) return reply([
      {id: 1, title: '待审批请假', status: 'pending', related_type: 'student_admin_service', related_id: 15},
      {id: 2, title: '待处理投诉', status: 'pending', related_type: 'student_feedback_ticket', related_id: 1},
      {id: 3, title: '自己的手工待办', status: 'pending', todo_type: 'custom'},
    ])
    return reply([])
  })
  await page.goto('/tickets')
  await expect(page.getByRole('button', {name: '受理', exact: true})).toHaveCount(1)
  await page.getByRole('button', {name: '受理', exact: true}).click()
  const modal = page.getByRole('dialog', {name: '核对后处理工单'})
  await expect(modal).toContainText('主管核实服务')
  await modal.getByRole('button', {name: '确认提交'}).click()
  await expect(page.getByRole('button', {name: '提交处理结果', exact: true})).toHaveCount(1)
  await page.goto('/todos')
  await expect(page.getByRole('link', {name: '办理来源事项'})).toHaveCount(2)
  await expect(page.getByRole('row').filter({hasText: '待审批请假'}).getByRole('button', {name: '处理', exact: true})).toHaveCount(0)
  await expect(page.getByRole('row').filter({hasText: '待处理投诉'}).getByRole('button', {name: '处理', exact: true})).toHaveCount(0)
  await expect(page.getByRole('row').filter({hasText: '自己的手工待办'}).getByRole('button', {name: '处理', exact: true})).toHaveCount(1)
})
