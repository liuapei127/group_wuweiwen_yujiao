import {readFileSync} from 'node:fs'
import {fileURLToPath} from 'node:url'
import {expect,type APIRequestContext,type Page} from '@playwright/test'
export interface Account {username:string;password:string;role:string}
export const roles=['admin','employee','manager','team_leader'] as const
export function accounts():Account[]{
  const file=process.env.ENT_PORTAL_CREDENTIALS||fileURLToPath(new URL('../../logs/ent-portal-local-credentials.json',import.meta.url))
  let data:{accounts?:Account[]}
  try{data=JSON.parse(readFileSync(file,'utf8'))}catch{throw new Error('缺少可读的四角色联调凭据文件：'+file)}
  const selected=roles.map(role=>{
    const matches=(data.accounts||[]).filter(a=>a.role===role)
    if(matches.length!==1||!matches[0].username||!matches[0].password)throw new Error('缺少唯一且完整的角色账号：'+role)
    return matches[0]
  })
  if(new Set(selected.map(a=>a.username)).size!==4)throw new Error('四角色需使用不同登录账号')
  return selected
}
export async function ready(request:APIRequestContext){
  const response=await request.get('/api/v1/auth/status',{timeout:10000})
  expect(response.status(),'前端代理必须连接到已启动的门户API').toBe(200)
  const body=await response.json()
  expect(body.code).toBe(0)
  expect(body.data).toMatchObject({mode:'trusted_jwt',ready:true})
}
export async function login(page:Page,account:Account){
  await page.goto('/')
  await page.getByLabel('员工账号').fill(account.username)
  await page.getByLabel('登录密码').fill(account.password)
  const [response]=await Promise.all([page.waitForResponse(r=>r.request().method()==='POST'&&r.url().endsWith('/api/v1/auth/login')),page.getByRole('button',{name:'登录工作台'}).click()])
  expect(response.status(),'账号需要真实登录成功').toBe(200)
  const data=await response.json()
  expect(data.code).toBe(0)
  const token=data.data?.access_token
  expect(typeof token).toBe('string')
  try{
    expect(data.data.user.role_code).toBe(account.role)
    expect(data.data.user.username).toBe(account.username)
    await expect(page.locator('.app-shell')).toBeVisible()
  }catch(error){await release(page.request,token);throw error}
  return token as string
}
export async function release(request:APIRequestContext,token:string){
  const headers={Authorization:'Bearer '+token}
  const response=await request.post('/api/v1/auth/logout',{headers})
  expect([200,401],'测试会话应退出或已经失效').toContain(response.status())
  const me=await request.get('/api/v1/auth/me',{headers})
  expect(me.status(),'退出后的令牌必须失效').toBe(401)
}
