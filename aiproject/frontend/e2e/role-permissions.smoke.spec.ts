import {test,expect,type Page} from '@playwright/test'

test.use({serviceWorkers:'block'})

const permissions=[
  {code:'roles:manage',name:'管理角色和功能权限',group:'角色权限',system_admin:true},
  {code:'classes:manage',name:'维护班级、班主任和班级名册',group:'学生事务',system_admin:true},
  {code:'crm:read',name:'查询本人客户、详情和跟进',group:'客户管理',system_admin:false},
  {code:'crm:write',name:'创建、修改客户及跟进',group:'客户管理',system_admin:false},
]

async function setup(page:Page,roleCode:string,failCatalog=false){
  let saved:Record<string,unknown>|undefined
  let failed=failCatalog
  const role={id:1,role_code:roleCode,role_name:'测试角色',description:'',status:1,permissions:['roles:manage']}
  await page.addInitScript(()=>sessionStorage.setItem('ent-token','isolated-role-test'))
  await page.route('**/api/v1/**',async route=>{
    const path=new URL(route.request().url()).pathname
    const reply=(data:unknown)=>route.fulfill({json:{code:0,data}})
    if(path.endsWith('/auth/me'))return reply({id:10,username:'19900001101',real_name:'测试管理员',role_code:'admin',role_name:'管理员',permissions:['roles:manage'],student_ids:[]})
    if(path.endsWith('/auth/permissions')){
      if(failed){failed=false;return route.fulfill({status:503,json:{detail:'权限目录加载失败'}})}
      return reply(permissions)
    }
    if(path.endsWith('/auth/roles/1')){saved=route.request().postDataJSON();return reply(role)}
    if(path.endsWith('/auth/roles'))return reply([role])
    return reply([])
  })
  await page.goto('/settings/roles')
  await page.getByRole('button',{name:'配置权限',exact:true}).click()
  return ()=>saved
}

test('admin automatically has the complete catalog and saves all grants',async({page})=>{
  const saved=await setup(page,'admin')
  const dialog=page.getByRole('dialog')
  await dialog.getByRole('tab',{name:'功能权限',exact:true}).click()
  await expect(dialog.getByRole('checkbox',{name:'查询本人客户、详情和跟进',exact:true})).toBeChecked()
  await expect(dialog.getByRole('checkbox')).toHaveCount(permissions.length)
  await expect(dialog.locator('.permission-toolbar')).toContainText('共 4 项 · 已选 4 项')
  await expect(dialog.getByRole('button',{name:/^清\s*空$/})).toBeDisabled()
  await dialog.getByRole('button',{name:'保存权限',exact:true}).click()
  await expect(dialog).toBeHidden()
  expect(saved()?.permissions).toEqual(permissions.map(p=>p.code))
})

test('shared menu grants stay synchronized and preserve function selections',async({page})=>{
  const saved=await setup(page,'advisor')
  const dialog=page.getByRole('dialog')
  await dialog.getByRole('tab',{name:'功能权限',exact:true}).click()
  await dialog.getByRole('checkbox',{name:'创建、修改客户及跟进',exact:true}).check()
  await dialog.getByRole('tab',{name:/菜单权限/}).click()
  const classGrant=dialog.getByRole('row').filter({hasText:'班级管理'}).getByRole('checkbox')
  await classGrant.check()
  await expect(dialog.getByRole('row').filter({hasText:'老师管理'}).getByRole('checkbox')).toBeChecked()
  await dialog.getByRole('button',{name:'保存权限',exact:true}).click()
  await expect(dialog).toBeHidden()
  expect(saved()?.permissions).toEqual(['roles:manage','crm:write','classes:manage'])
})

test('failed catalog blocks saving and offers a working retry',async({page})=>{
  await setup(page,'admin',true)
  const dialog=page.getByRole('dialog')
  await expect(dialog.getByText('权限目录加载失败',{exact:true})).toBeVisible()
  await expect(dialog.getByRole('button',{name:'保存权限',exact:true})).toBeDisabled()
  await dialog.getByRole('button',{name:'重新加载权限目录',exact:true}).click()
  await expect(dialog.getByRole('button',{name:'保存权限',exact:true})).toBeEnabled()
  await dialog.getByRole('tab',{name:'功能权限',exact:true}).click()
  await expect(dialog.getByRole('checkbox')).toHaveCount(permissions.length)
})
