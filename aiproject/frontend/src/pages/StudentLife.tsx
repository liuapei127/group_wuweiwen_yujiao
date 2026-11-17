import {useState} from 'react'
import {Alert, Button, Collapse, Empty, Input, Modal, Segmented, Space, Tag, Typography} from 'antd'
import {useQuery} from '@tanstack/react-query'
type Request = <T>(path: string, method?: string, body?: unknown) => Promise<T>
type FAQ = {question: string; answer: string; source_title: string; source_url: string}
type Resource = {id: number; title: string; category: string; content: string; country?: string; city?: string; source_title?: string; source_url?: string; verified_at?: string; details?: {scope: string; summary: string; steps: string[]; faqs: FAQ[]; contacts: {label: string; number: string}[]; sources: {title: string; url: string}[]}}
const categories = [{key:'arrival',label:'到达与安顿',caption:'从落地到安顿下来'}, {key:'medical',label:'医疗与保险',caption:'提前了解就医准备'}, {key:'transport',label:'交通出行',caption:'找到适合你的路线'}, {key:'housing',label:'住宿租房',caption:'安心找房，仔细核对'}, {key:'study',label:'学习支持',caption:'为学习留出一点空间'}, {key:'emergency',label:'紧急求助',caption:'把重要联系方式放在手边'}]
const names: Record<string,string> = {Germany:'德国',Singapore:'新加坡'}
const url = (value?: string) => value?.startsWith('https://') ? value : undefined
export function StudentLife({request, chat}: {request: Request; chat: (query: string) => void}) {
  const [country, setCountry] = useState('')
  const [category, setCategory] = useState('')
  const [keyword, setKeyword] = useState('')
  const [selected, setSelected] = useState<Resource>()
  const [copied, setCopied] = useState('')
  const profile = useQuery({queryKey:['visitor','student','profile'],queryFn:()=>request<{abroad_country?:string}>('/api/v1/student/profile')})
  const registered = profile.data?.abroad_country
  const target = country || (registered && names[registered] ? registered : '')
  const result = useQuery({queryKey:['visitor','student','overseas',target,category,keyword],enabled:!!target,queryFn:()=>request<{items:Resource[]}>('/api/v1/student/overseas-life?'+new URLSearchParams({country:target,category,keyword,limit:'50'}))})
  async function copy(number: string) {try {await navigator.clipboard.writeText(number);setCopied(number)} catch {setCopied('复制未成功，请选中号码手动复制')}}
  const emergency = useQuery({queryKey:['visitor','student','life-emergency',target],enabled:!!target,queryFn:()=>request<{items:Resource[]}>('/api/v1/student/overseas-life?'+new URLSearchParams({country:target,category:'emergency',limit:'10'}))})
  const urgent = emergency.data?.items[0]?.details?.contacts.slice(0,2) || []

  return <div className="stu-life"><header className="stu-life__intro"><div><span className="stu-overline">LIFE, A LITTLE EASIER</span><h2>把异乡，慢慢过成熟悉的日常。</h2><p>先看关键答案，再了解具体步骤。需要一起找答案时，也可以问学生助手。</p></div><Segmented aria-label="生活资料地区" value={target} options={[{label:'德国',value:'Germany'},{label:'新加坡',value:'Singapore'}]} onChange={value=>{setCountry(String(value));setSelected(undefined);setCopied('')}}/></header>
    <p className="stu-life__scope">当前浏览：{names[target] || '请选择地区'}{target===registered?' · 按学籍留学方向默认展示':''}。这里可切换资料地区，不会更改你的学籍或实际位置。</p>
    {!!target && urgent.length > 0 && <section className="stu-life__urgent" aria-label="重要求助电话"><div><strong>{names[target]} · 重要求助电话</strong><small>按当前浏览地区展示，使用前确认本人所在地</small></div><div>{urgent.map(contact=><button key={contact.number} onClick={()=>void copy(contact.number)} aria-label={'复制'+contact.label+contact.number}><small>{contact.label}</small><strong>{contact.number}</strong><span>{copied===contact.number?'已复制':'复制号码'}</span></button>)}</div><Button type="link" onClick={()=>{setCategory('emergency');setKeyword('')}}>查看求助指南 →</Button></section>}
    <div className="stu-life__filters"><Space wrap><Button type={!category?'primary':'default'} onClick={()=>setCategory('')}>全部指南</Button>{categories.map(item=><Button key={item.key} type={category===item.key?'primary':'default'} onClick={()=>setCategory(item.key)}>{item.label}</Button>)}</Space><Input.Search aria-label="搜索生活问题" placeholder="试试：报警电话、银行卡乘车、租房押金…" allowClear maxLength={64} onSearch={value=>setKeyword(value.trim())}/></div>
    {result.error&&<Alert type="error" showIcon title={(result.error as Error).message}/>}
    {result.isFetching&&<p>正在找相关资料…</p>}
    {!result.isFetching&&!result.error&&!result.data?.items.length&&<Empty description={target?'没有匹配资料，试试其他关键词或问问助手':'先选择你想了解的国家'}/>}
    <div className="stu-life__grid">{(result.data?.items||[]).map(item=>{const index=Math.max(0,categories.findIndex(category=>category.key===item.category));const style={backgroundImage:'url(/images/student-'+(target==='Singapore'?'singapore':'germany')+'-life.png)',backgroundSize:'300% auto',backgroundPosition:(index%3)*50+'% '+(index<3?14:86)+'%'};return <article className="stu-life-card" key={item.id}><button className="stu-life-card__photo" style={style} onClick={()=>setSelected(item)} aria-label={'查看'+item.title}><span>{categories[index]?.label}</span><small>场景示意</small></button><div className="stu-life-card__body"><span className="stu-overline">{categories[index]?.caption}</span><h3>{item.title}</h3><p>{item.details?.summary||item.content}</p><div className="stu-life-card__meta">{names[item.country||target]} · 核对于 {item.verified_at?.slice(0,10)||'尚未登记'}</div><Space><Button type="primary" onClick={()=>setSelected(item)}>阅读指南</Button><Button type="link" onClick={()=>chat(names[target]+'：'+(item.details?.faqs[0]?.question||item.title))}>问问助手 →</Button></Space></div></article>})}</div>
    <Modal title={selected?.title} open={!!selected} onCancel={()=>{setSelected(undefined);setCopied('')}} width={800} footer={<Space><Button onClick={()=>setSelected(undefined)}>关闭</Button><Button type="primary" onClick={()=>{if(selected)chat(names[target]+'：'+(selected.details?.faqs[0]?.question||selected.title));setSelected(undefined)}}>和助手继续聊</Button></Space>}>
      <p className="stu-life__scope">{selected?.details?.scope||names[target]} · 核对日期：{selected?.verified_at?.slice(0,10)}</p><Typography.Paragraph>{selected?.details?.summary||selected?.content}</Typography.Paragraph>
      {!!selected?.details?.contacts.length&&<section className="stu-life__contacts"><h3>常用联系方式</h3>{selected.details.contacts.map(contact=><div key={contact.number}><span>{contact.label}</span><strong>{contact.number}</strong><Button onClick={()=>void copy(contact.number)}>{copied===contact.number?'已复制':'复制'}</Button><a href={'tel:'+contact.number.replaceAll(' ','')}>拨打</a></div>)}</section>}
      {!!selected?.details?.steps.length&&<><h3>可以按这些步骤准备</h3><ol className="stu-life__steps">{selected.details.steps.map(step=><li key={step}>{step}</li>)}</ol></>}
      {!!selected?.details?.faqs.length&&<><h3>常见问题</h3><Collapse items={selected.details.faqs.map((faq,index)=>({key:index,label:faq.question,children:<><p>{faq.answer}</p>{url(faq.source_url)&&<a href={url(faq.source_url)} target="_blank" rel="noopener noreferrer">{faq.source_title} · 官方详情 ↗</a>}</>}))}/></>}
      <h3>信息来源</h3><div className="stu-life__sources">{(selected?.details?.sources||[{title:selected?.source_title||'官方来源',url:selected?.source_url||''}]).map(source=>url(source.url)&&<a key={source.url} href={url(source.url)} target="_blank" rel="noopener noreferrer">{source.title} ↗</a>)}</div><Tag>资料地区与实际所在地需分别核对</Tag>
    </Modal>
  </div>
}
