import {expect,test} from '@playwright/test'

test.use({serviceWorkers:'block'})
for(const entry of ['customer','intake']){
  test(entry+' shows owned visitor reservations and live check-in updates',async({page})=>{
    let attended=false
    let forbidden=false
    const visitor={visitor_id:42,name:'预约测试游客',nickname:'测试',contact:'13900000000',
      registered_at:'2026-11-18T01:00:00Z',claimed_at:'2026-11-18T01:00:00Z',
      last_contact_at:null,manual_source_id:null,crm_lead_id:10}
    await page.addInitScript(()=>sessionStorage.setItem('ent-token','advisor-booking-ui'))
    await page.route('**/api/v1/**',route=>{
      const url=new URL(route.request().url())
      const path=url.pathname
      const reply=(data:unknown)=>route.fulfill({json:{code:0,data}})
      if(path.endsWith('/auth/me'))return reply({id:10,real_name:'顾问',role_name:'顾问',role_code:'employee',
        permissions:['crm:read','visitor-intake:read'],student_ids:[]})
      if(path.endsWith('/42/reservations')){
        expect(url.searchParams.get('limit')).toBe('20')
        if(forbidden)return route.fulfill({status:404,json:{detail:'游客联系记录不存在'}})
        const reservation={id:100,event_id:5,event_name:'德国升学说明会',event_status:'upcoming',
          location:'广州教学中心',start_time:'2026-11-25T06:00:00',end_time:'2026-11-25T08:00:00',
          status:attended?'attended':'registered',reserved_at:'2026-11-18T09:45:00',
          attended_at:attended?'2026-11-25T06:05:00':null,cancelled_at:null}
        if(url.searchParams.has('before_id')){
          expect(url.searchParams.get('before_id')).toBe('81')
          return reply([{...reservation,id:80,event_name:'历史取消活动',status:'cancelled',
            cancelled_at:'2026-11-18T10:00:00',attended_at:null}])
        }
        return reply(Array.from({length:20},(_,i)=>({...reservation,id:100-i,event_name:i?'其他活动 '+i:reservation.event_name})))
      }
      if(path.endsWith('/visitor-intake/assigned'))return reply([visitor])
      if(path.endsWith('/visitor-intake/42'))return reply(visitor)
      if(path.endsWith('/profile')){
        if(url.searchParams.has('watch_version'))return route.fulfill({contentType:'text/event-stream',
          body:'event: result\ndata: {"data":{"changed":false}}\n\n'})
        return reply({customer_name:visitor.name,version:0,visitor_id:42,
          readiness:{ready:false,missing_fields:[]},screening_input:[]})
      }
      if(path.endsWith('/leads/10'))return reply({lead:{id:10,customer_name:visitor.name,status:'contacting'},follow_ups:[]})
      return reply([])
    })
    await page.goto(entry==='customer'?'/customers/10':'/visitor-intake')
    if(entry==='intake'){
      await page.getByRole('tab',{name:'我已认领'}).click()
      await page.getByRole('button',{name:'预约与签到',exact:true}).click()
    }
    const card=page.locator('.ant-card').filter({has:page.getByText('活动预约与签到',{exact:true})})
    await expect(card).toBeVisible()
    const row=card.getByRole('row').filter({hasText:'德国升学说明会'})
    await expect(row).toContainText('已预约')
    // Event dates use Beijing local time and must not acquire another eight hours.
    await expect(row).toContainText('2026-11-25 06:00')
    await expect(card.getByRole('button',{name:'签到',exact:true})).toHaveCount(0)
    attended=true
    await card.getByRole('button',{name:'刷新预约',exact:true}).click()
    await expect(row).toContainText('已签到')
    await expect(row).toContainText('2026-11-25 06:05')
    await card.getByRole('button',{name:'查看更多预约'}).click()
    await expect(card.getByRole('row').filter({hasText:'历史取消活动'})).toContainText('已取消')
    await expect(card.getByRole('row').filter({hasText:'历史取消活动'})).toContainText('2026-11-18 10:00')
    await card.getByRole('button',{name:'返回最新预约'}).click()
    await expect(row).toContainText('已签到')
    forbidden=true
    await card.getByRole('button',{name:'刷新预约',exact:true}).click()
    await expect(card.getByText('游客联系记录不存在',{exact:true})).toBeVisible()
    await expect(row).toHaveCount(0)
  })
}
