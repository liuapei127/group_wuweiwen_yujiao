import {expect,test} from '@playwright/test'
import {readFileSync} from 'node:fs'

// Exercise the UI against the server's complete catalogue, without a live database.
const rbac=readFileSync(new URL('../../app/core/security/rbac.py',import.meta.url),'utf8')
const definitions=rbac.split('PERMISSIONS = {')[1].split('\n}')[0]
const catalog=Array.from(definitions.matchAll(/'([^']+)': \('([^']+)', '([^']+)'\)/g),match=>({
  code:match[1],name:match[2],group:match[3],system_admin:true,
}))

test.describe('complete role menu permissions',()=>{
  test.use({serviceWorkers:'block'})
  for(const roleCode of ['manager','admin']){
    test(roleCode+' sees all menu entries and saves eligible permissions',async({page})=>{
      const role={id:2,role_code:roleCode,role_name:'待配置角色',status:1,permissions:[] as string[]}
      let saved:string[]|undefined
      await page.addInitScript(()=>sessionStorage.setItem('ent-token','roles-test'))
      await page.route('**/api/v1/**',async route=>{
        const path=new URL(route.request().url()).pathname
        const reply=(data:unknown)=>route.fulfill({json:{code:0,data}})
        if(path==='/api/v1/auth/me')return reply({id:1,real_name:'权限管理员',role_code:'admin',role_name:'管理员',permissions:['roles:manage']})
        if(path==='/api/v1/auth/permissions')return reply(catalog)
        if(path==='/api/v1/auth/roles/2'){
          saved=route.request().postDataJSON().permissions
          role.permissions=saved!
          return reply(role)
        }
        if(path==='/api/v1/auth/roles')return reply([role])
        return reply({})
      })
      await page.goto('/settings/roles')
      await page.getByRole('button',{name:'配置权限',exact:true}).click()
      const dialog=page.getByRole('dialog',{name:'配置角色权限'})
      const menus=dialog.getByRole('tabpanel')
      const navigationSource=readFileSync(new URL('../src/navigation.tsx',import.meta.url),'utf8')
      const menuNames=Array.from(navigationSource.matchAll(/path:'[^']+',title:'([^']+)'/g),match=>match[1])
      expect(menuNames.length).toBeGreaterThan(30)
      for(const title of menuNames)await expect(menus.getByRole('row').filter({has:page.getByText(title,{exact:true})})).toHaveCount(1)
      const reporting=menus.getByRole('row').filter({hasText:'智报中心'})
      const operations=reporting.getByRole('checkbox',{name:/^查看授权范围内的经营与投诉统计/})
      if(roleCode==='admin'){
        await expect(operations).toBeDisabled()
        await expect(operations).toBeChecked()
        await expect(dialog.getByText(/管理员固定拥有全部功能权限/)).toBeVisible()
      }else{
        await operations.check()
        const classes=menus.getByRole('row').filter({hasText:'班级管理'})
        await classes.getByRole('checkbox').check()
        await expect(menus.getByRole('row').filter({hasText:'老师管理'}).getByRole('checkbox')).toBeChecked()
        await dialog.getByRole('tab',{name:'功能权限',exact:true}).click()
        await expect(dialog.getByRole('tabpanel').getByRole('checkbox',{name:'查看授权范围内的经营与投诉统计',exact:true})).toBeChecked()
        await dialog.getByRole('tabpanel').getByRole('checkbox',{name:'生成授权范围内的员工正式报告',exact:true}).check()
        await dialog.getByRole('tab',{name:/菜单权限/}).click()
        await expect(operations).toBeChecked()
      }
      if(roleCode==='admin')await expect(dialog.getByRole('button',{name:/^清\s*空$/})).toBeDisabled()
      await dialog.getByRole('button',{name:'保存权限',exact:true}).click()
      await expect(dialog).toBeHidden()
      expect(saved?.sort()).toEqual(roleCode==='admin'
        ? catalog.filter(p=>p.system_admin).map(p=>p.code).sort()
        : ['reports:operations:read','classes:manage','reports:formal:generate'].sort())
    })
  }
})
