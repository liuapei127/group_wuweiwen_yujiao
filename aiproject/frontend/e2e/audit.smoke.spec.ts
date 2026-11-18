import {test,expect,type Page} from '@playwright/test'

test.use({serviceWorkers:'block'})

async function setup(page:Page){
  await page.addInitScript(()=>sessionStorage.setItem('ent-token','isolated-audit-test'))
  await page.route('**/api/v1/**',async route=>{
    const path=new URL(route.request().url()).pathname
    const reply=(data:unknown)=>route.fulfill({json:{code:0,data}})
    if(path.endsWith('/auth/me'))return reply({id:10,username:'19900001101',real_name:'测试管理员',role_code:'admin',role_name:'管理员',permissions:['audit:read'],student_ids:[]})
    if(path.endsWith('/auth/audit'))return reply([
      {id:41,actor_id:10,action:'login',target:'19900001101',details:{},create_time:'2026-11-18T01:19:02'},
      {id:40,actor_id:11,action:'role_save',target:'advisor',details:{permissions:['crm:read'],status:0},create_time:'2026-11-18T01:17:50'},
    ])
    return reply([])
  })
  await page.goto('/settings/audit')
}

test('audit without supplemental data still shows the complete event',async({page})=>{
  await setup(page)
  await page.getByRole('row').filter({hasText:'19900001101'}).getByRole('button',{name:'查看',exact:true}).click()
  const drawer=page.getByRole('dialog',{name:'审计详情'})
  await expect(drawer.getByText('41',{exact:true})).toBeVisible()
  await expect(drawer.getByText('2026-11-18T01:19:02',{exact:true})).toBeVisible()
  await expect(drawer.getByText('10',{exact:true})).toBeVisible()
  await expect(drawer.getByText('登录',{exact:true})).toBeVisible()
  await expect(drawer.getByText('19900001101',{exact:true})).toBeVisible()
  await expect(drawer.getByText('无额外操作详情',{exact:true})).toBeVisible()
})

test('audit switches records and retains nested supplemental data',async({page})=>{
  await setup(page)
  await page.getByRole('row').filter({hasText:'19900001101'}).getByRole('button',{name:'查看',exact:true}).click()
  const drawer=page.getByRole('dialog',{name:'审计详情'})
  await drawer.getByRole('button',{name:'关闭',exact:true}).click()
  await expect(drawer).toBeHidden()
  await page.getByRole('row').filter({hasText:'advisor'}).getByRole('button',{name:'查看',exact:true}).click()
  await expect(drawer.getByText('40',{exact:true})).toBeVisible()
  await expect(drawer.getByText('11',{exact:true})).toBeVisible()
  await expect(drawer.getByText('保存角色权限',{exact:true})).toBeVisible()
  await expect(drawer.getByText('advisor',{exact:true})).toBeVisible()
  await expect(drawer.locator('.json-value')).toContainText('"permissions": [')
  await expect(drawer.locator('.json-value')).toContainText('"crm:read"')
  await expect(drawer.locator('.json-value')).toContainText('"status": 0')
  await expect(drawer.getByText('无额外操作详情',{exact:true})).toHaveCount(0)
})
