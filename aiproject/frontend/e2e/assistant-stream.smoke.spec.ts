import {expect,test} from '@playwright/test'

test.use({serviceWorkers:'block'})
for(const interrupted of [false,true]){
  test('employee assistant '+(interrupted?'handles an interrupted stream without retrying':'shows concrete partial text before the final result and restores it'),async({page})=>{
    const cid='11111111-1111-4111-8111-111111111111'
    const content='本次返回 1 条待办：\n\n1. 待办编号：378\n标题：待处理投诉\n状态：待处理\n优先级：中\n到期时间：2026-11-18 10:16:22\n关联编号：271'
    const completed={id:cid,title:'待办查询',version:1,messages:[
      {id:1,role:'user',content:'查询我的到期待办'}, {id:2,role:'assistant',content},
    ]}
    let saved=false
    await page.addInitScript(({cid,completed,interrupted})=>{
      sessionStorage.setItem('ent-token','employee-stream-test')
      const original=window.fetch.bind(window)
      const state=window as typeof window&{finishAssistantStream?:()=>void;assistantStreamCalls?:number}
      window.fetch=async(input,init)=>{
        if(String(input).endsWith('/'+cid+'/messages')){
          if(new Headers(init?.headers).get('Accept')!=='text/event-stream')throw new Error('Missing streaming Accept header')
          state.assistantStreamCalls=(state.assistantStreamCalls||0)+1
          const encoder=new TextEncoder()
          const stream=new ReadableStream({start(controller){
            controller.enqueue(encoder.encode('event: text\ndata: '+JSON.stringify({text:'本次返回 1 条待办：\n标题：待处理投诉'})+'\n\n'))
            state.finishAssistantStream=()=>{
              if(interrupted){controller.close();return}
              controller.enqueue(encoder.encode('event: text\ndata: '+JSON.stringify({text:completed.messages[1].content})+'\n\n'))
              controller.enqueue(encoder.encode('event: result\ndata: '+JSON.stringify({data:completed})+'\n\n'))
              controller.close()
            }
          }})
          return new Response(stream,{headers:{'Content-Type':'text/event-stream'}})
        }
        return original(input,init)
      }
    },{cid,completed,interrupted})
    await page.route('**/api/v1/**',route=>{
      const path=new URL(route.request().url()).pathname
      const reply=(data:unknown)=>route.fulfill({json:{code:0,data}})
      if(path.endsWith('/auth/me'))return reply({id:10,real_name:'班主任',role_name:'班主任',role_code:'team_leader',
        permissions:['ai:use','todos:read'],student_ids:[]})
      if(path.endsWith('/conversations'))return reply([{id:cid,title:'待办查询',version:saved?1:0}])
      if(path.endsWith('/'+cid))return reply(saved?completed:{id:cid,title:'待办查询',version:0,messages:[]})
      return reply([])
    })
    await page.goto('/assistant')
    await page.getByRole('button',{name:/待办查询$/}).click()
    await page.getByRole('textbox',{name:'发送给AI的消息'}).fill('查询我的到期待办')
    await page.getByRole('button',{name:'发送',exact:true}).click()
    const log=page.getByRole('log',{name:'消息记录'})
    await expect(log.getByText('正在输出…',{exact:true})).toBeVisible()
    await expect(log).toContainText('标题：待处理投诉')
    await expect(log).not.toContainText('关联编号：271')
    await expect(log).toHaveAttribute('aria-busy','true')
    saved=!interrupted
    await page.evaluate(()=>{(window as typeof window&{finishAssistantStream:()=>void}).finishAssistantStream()})
    await expect(log).toHaveAttribute('aria-busy','false')
    await expect(log.getByText('正在输出…',{exact:true})).toHaveCount(0)
    if(interrupted){
      await expect(page.getByText('回复连接中断，请先查看记录后再试。',{exact:true})).toBeVisible()
      expect(await page.evaluate(()=>(window as typeof window&{assistantStreamCalls:number}).assistantStreamCalls)).toBe(1)
    }else{
      await expect(log).toContainText('关联编号：271')
      await expect(log).toContainText('到期时间：2026-11-18 10:16:22')
      await expect(log).not.toContainText('assignee_id')
      await expect(log).not.toContainText('后端查询结果')
      await page.reload()
      await page.getByRole('button',{name:/待办查询$/}).click()
      await expect(log).toContainText('关联编号：271')
    }
  })
}
