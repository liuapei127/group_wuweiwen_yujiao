import {expect,test} from '@playwright/test'
import {accounts,ready,login,release} from './helpers'

test('real AI: confirm, cancel, write once, query and reject duplicate confirmation',async({page,request})=>{
  test.setTimeout(180000)
  await ready(request)
  const token=await login(page,accounts().find(a=>a.role==='employee')!)
  const headers={Authorization:'Bearer '+token}
  const title='ENT-AI-E2E-'+Date.now()
  try{
    const health=await request.get('/api/v1/portal/health',{headers})
    expect(health.status()).toBe(200)
    expect((await health.json()).data.ai_configured,'AI项目要求真实Dify接入，不能静默跳过').toBe(true)
    await page.goto('/assistant')
    const input=page.getByRole('textbox',{name:'发送给AI的消息'})
    async function turn(action:()=>Promise<void>){
      const [response]=await Promise.all([page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/messages'),{timeout:90000}),action()])
      expect(response.status()).toBe(200)
      const body=await response.json();expect(body.code).toBe(0)
      return body.data
    }
    async function send(text:string){return turn(async()=>{await input.fill(text);await page.getByRole('button',{name:/发送$/}).click()})}
    async function rows(){
      const response=await request.get('/api/v1/enterprise/todos?limit=100',{headers})
      expect(response.status()).toBe(200)
      const body=await response.json();expect(body.code).toBe(0)
      return (body.data as Array<{id:number;title:string}>).filter(r=>r.title===title)
    }
    const draft=await send('新增待办，标题为'+title+'，说明为本地AI验收合成数据')
    expect(draft.pending).toMatchObject({intent:'todo_create',state:'confirm',params:{title}})
    expect(draft.messages.at(-1).metadata.source).toBe('Dify')
    expect(draft.messages.at(-1).metadata.executed).toBe(false)
    expect(await rows()).toHaveLength(0)
    const cancelled=await turn(()=>page.getByRole('button',{name:'取消操作'}).click())
    expect(cancelled.pending).toBeNull();expect(cancelled.messages.at(-1).content).toContain('已取消')
    expect(await rows()).toHaveLength(0)
    const afterCancel=await send('确认')
    expect(afterCancel.messages.at(-1).content).toContain('没有待确认')
    expect(afterCancel.messages.at(-1).metadata.executed).toBe(false)
    expect(await rows()).toHaveLength(0)
    const second=await send('新增待办，标题为'+title+'，说明为本地AI验收合成数据')
    expect(second.pending?.state).toBe('confirm')
    const saved=await turn(()=>page.getByRole('button',{name:'确认执行'}).click())
    expect(saved.pending).toBeNull()
    expect(saved.messages.at(-1).metadata).toMatchObject({action:'todo_create',executed:true,http_status:200})
    expect(saved.messages.at(-1).content).toContain('已确认操作成功')
    const created=await rows();expect(created).toHaveLength(1);expect(created[0].id).toBeGreaterThan(0)
    const replay=await send('确认')
    expect(replay.messages.at(-1).content).toContain('没有待确认')
    expect(replay.messages.at(-1).metadata.executed).toBe(false)
    expect(await rows()).toHaveLength(1)
    const found=await send('查询我的待办')
    expect(found.messages.at(-1).metadata).toMatchObject({action:'todos',executed:true,http_status:200})
    expect(found.messages.at(-1).content).toContain(title)
    expect(await rows()).toHaveLength(1)
  }finally{await release(page.request,token)}
})
