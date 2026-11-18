import {expect,test} from '@playwright/test'

test.use({serviceWorkers:'block'})
for(const empty of [false,true]){
  test('manager charts '+(empty?'remain visible for an empty authorized scope':'keep drill-downs and use Chinese labels'),async({page})=>{
    const customers={department:'所管组织及下级',leads_by_status:{new:28},transitions:{signed:7,lost:2},
      departments:[{department:'升学咨询部',new:28,signed:7,lost:2}],follow_ups:{phone:10},lost_reasons:{},items:[],has_more:false}
    await page.addInitScript(()=>sessionStorage.setItem('ent-token','manager-chart-test'))
    await page.route('**/api/v1/**',route=>{
      const url=new URL(route.request().url())
      const path=url.pathname
      const reply=(data:unknown)=>route.fulfill({json:{code:0,data}})
      if(path.endsWith('/auth/me'))return reply({id:9,real_name:'主管',role_name:'主管',role_code:'manager',
        permissions:['reports:operations:read'],student_ids:[]})
      if(path.endsWith('/customers/analysis'))return reply({groups:{intended_project:[{label:'sg_hospitality',count:7,signed:2,signed_percent:28.6}]}})
      if(path.endsWith('/board/customers')){
        const metric=url.searchParams.get('metric')
        if(metric==='signed'){
          expect(url.searchParams.get('department')).toBe('升学咨询部')
          return reply({...customers,items:[{id:1,customer_name:'部门签约客户',status:'signed'}]})
        }
        if(metric==='project'){
          expect(url.searchParams.get('bucket')).toBe('sg_hospitality')
          return reply({...customers,items:[{id:2,customer_name:'酒店项目客户',status:'new',intended_project:'sg_hospitality'}]})
        }
        return reply(customers)
      }
      if(path.endsWith('/board/complaints'))return reply({department:'所管组织及下级',
        complaints_by_status:empty?{}:{pending:7,resolved:6},categories:empty?{}:{learning:16,company:7},
        backlog:{'0–2 天':empty?0:5,'3–6 天':0,'7–13 天':0,'14 天以上':0},
        satisfaction:empty?{}:{'5':10},items:[],has_more:false})
      if(path.endsWith('/complaints/analysis'))return reply({})
      return reply([])
    })
    await page.goto('/reporting')
    await expect(page.getByRole('region',{name:'部门经营对比',exact:true})).toHaveCount(1)
    await expect(page.getByText('分部门经营明细',{exact:true})).toHaveCount(0)
    await page.getByRole('button',{name:'升学咨询部 · 签约记录 · 7 条明细',exact:true}).click()
    const department=page.getByRole('dialog',{name:'升学咨询部 · 签约记录'})
    await expect(department).toContainText('部门签约客户')
    await department.getByRole('button',{name:'关闭',exact:true}).click()
    await page.getByRole('button',{name:'意向项目 · 新加坡酒店就业班 · 7 条明细',exact:true}).click()
    const project=page.getByRole('dialog',{name:'客户分组 · 新加坡酒店就业班'})
    await expect(project).toContainText('酒店项目客户')
    await expect(project).toContainText('新加坡酒店就业班')
    await expect(project).not.toContainText('sg_hospitality')
    await project.getByRole('button',{name:'关闭',exact:true}).click()
    await page.getByRole('button',{name:'投诉周报',exact:true}).click()
    for(const name of ['投诉状态','投诉分类','积压账龄','满意度分布']){
      const chart=page.getByRole('region',{name,exact:true})
      await expect(chart).toBeVisible()
      if(empty)await expect(chart).toContainText('当前授权范围和所选期间暂无数据')
    }
    if(!empty){
      await expect(page.getByRole('region',{name:'投诉分类',exact:true})).toContainText('学习类')
      await expect(page.getByRole('region',{name:'投诉分类',exact:true})).toContainText('公司服务类')
      await expect(page.getByRole('region',{name:'投诉分类',exact:true})).not.toContainText('learning')
    }
  })
}
