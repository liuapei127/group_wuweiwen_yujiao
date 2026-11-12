import {expect,test} from '@playwright/test'
import {accounts,roles,ready,login,release} from './helpers'

test.beforeAll(async({request})=>{await ready(request)})

test('auth status goes through the frontend dev proxy',async({request})=>{
  await ready(request)
})

for(const role of roles){
  test(role+' sees its role menus and controls',async({page})=>{
    const account=accounts().find(a=>a.role===role)!
    const token=await login(page,account)
    try{
      const menu=page.locator('.desktop-sider')
      const has=async(name:string)=>expect(menu.getByText(name,{exact:true})).toBeVisible()
      const absent=async(name:string)=>expect(menu.getByText(name,{exact:true})).toHaveCount(0)
      await has('工作台');await has('AI 助手');await has('我的待办')
      if(role==='admin'){
        for(const name of ['客户管理','学生成绩','请假审批','员工管理','角色权限','安全审计'])await has(name)
        await page.goto('/settings/users')
        await expect(page.getByRole('button',{name:'新增员工'})).toBeVisible()
      }else{
        for(const name of ['员工管理','角色权限','安全审计'])await absent(name)
        if(role==='team_leader'){
          await has('学生成绩');await has('请假审批');await absent('客户管理')
          await page.goto('/scores');await expect(page.getByRole('button',{name:'录入成绩'})).toBeVisible()
        }else{
          await has('客户管理');await absent('学生成绩');await absent('请假审批')
          await page.goto('/guides')
          if(role==='manager')await expect(page.getByRole('button',{name:'新增指南'})).toBeVisible()
          else await expect(page.getByRole('button',{name:'新增指南'})).toHaveCount(0)
          await page.goto('/directory')
          await page.getByRole('tab',{name:'查找同事'}).click()
          const search=page.getByPlaceholder('输入同事姓名后搜索')
          await search.fill('联调员工');await search.press('Enter')
          await expect(page.getByRole('cell',{name:'联调员工',exact:true})).toBeVisible()
          if(role==='manager')await expect(page.getByRole('button',{name:'查看联系方式'})).toBeVisible()
          else await expect(page.getByRole('button',{name:'查看联系方式'})).toHaveCount(0)
        }
        await page.goto('/settings/users')
        await expect(page.getByText('暂无访问权限',{exact:true})).toBeVisible()
        const denied=await page.request.get('/api/v1/auth/users',{headers:{Authorization:'Bearer '+token}})
        expect(denied.status()).toBe(403)
      }
      await page.locator('.user-menu').click()
      await page.getByText('退出登录',{exact:true}).click()
      await expect(page.getByRole('heading',{name:'登录你的工作空间'})).toBeVisible()
    }finally{await release(page.request,token)}
  })
}

test('anonymous requests are 401 and a logged-out token is revoked',async({request})=>{
  const anonymous=await request.get('/api/v1/portal/context')
  expect(anonymous.status()).toBe(401)
  const account=accounts().find(a=>a.role==='employee')!
  const response=await request.post('/api/v1/auth/login',{data:{username:account.username,password:account.password}})
  expect(response.status()).toBe(200)
  const data=await response.json();expect(data.code).toBe(0)
  const token=data.data.access_token
  try{
    const headers={Authorization:'Bearer '+token}
    expect((await request.get('/api/v1/auth/me',{headers})).status()).toBe(200)
    expect((await request.get('/api/v1/auth/users',{headers})).status()).toBe(403)
  }finally{await release(request,token)}
})

if(process.env.ENT_PORTAL_API){
  test('optional explicitly configured direct backend status',async({request})=>{
    const response=await request.get(process.env.ENT_PORTAL_API!.replace(/\/$/,'')+'/api/v1/auth/status')
    expect(response.status()).toBe(200)
    const body=await response.json();expect(body.code).toBe(0)
    expect(body.data).toMatchObject({mode:'trusted_jwt',ready:true})
  })
}
