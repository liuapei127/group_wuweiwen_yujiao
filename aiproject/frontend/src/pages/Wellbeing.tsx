import {useState} from 'react'
import {App, Button, Card, Form, Input, Select, Space, Table, Tag, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ActionModal, DetailDrawer, ErrorNotice, type ActionSpec} from '../components/shared'
import {api, query} from '../lib/api'
import {CountBars, Metric} from './ReportMetrics'
import {today} from './reportDates'
import {ReportHistory} from './ReportHistory'
import {WellbeingCharts, type WellbeingDistributionData} from './WellbeingCharts'
import {WellbeingTrend} from './ReportAnalysis'

const staff = '/api/v1/reporting/wellbeing'
const student = '/api/v1/student/wellbeing'
type Count = {day:string;label:string;count:number}
type Snapshot = WellbeingDistributionData & {period_start:string;period_end:string;eligible:number;participants:number|null;suppressed:boolean;
  emotion:Count[];stress:Count[];items:{status:string;risk_level:string;count:number}[]}
type Archive = Snapshot & {archive_id:number;ai_summary?:string;review_status:string}
type Case = {id:number;student_id:number;student_name?:string|null;note:string;status:string;created_at:string;followups?:unknown[]}
type Event = {id:number;day:string;title:string;note:string}
type Checkin = {day:string;emotion:string;stress:string}
type Panel = {version:string;description:string;granted:boolean;checkins:Checkin[]}
type Request = <T,>(path:string,method?:string,body?:unknown)=>Promise<T>
const emotion: Record<string,string> = {very_good:'非常好',good:'良好',neutral:'平稳',poor:'低落',very_poor:'很低落'}
const stress: Record<string,string> = {none:'无压力',light:'轻度',moderate:'中度',high:'较高'}
const caseStates: Record<string,string> = {open:'待跟进',following:'跟进中',closed:'已结案'}
const options = (labels:Record<string,string>) => Object.entries(labels).map(([value,label])=>({value,label}))

function DailyCheckins({data}:{data:Snapshot}) {
  const [selected,select]=useState<string>()
  const days=Array.from(new Set([...data.emotion,...data.stress].map(row=>row.day))).sort()
  const day=selected&&days.includes(selected)?selected:days[0]
  const counts=(rows:Count[])=>Object.fromEntries(rows.filter(row=>row.day===day).map(row=>[row.label,row.count]))
  if(!day)return <Card title="每日自评分布">
    <Typography.Text type="secondary">{data.suppressed?'本周参与人数低于展示门槛。':'各日分组暂无可展示数据。'}</Typography.Text>
  </Card>
  return <Space orientation="vertical" style={{width:'100%'}}>
    <Space wrap><Typography.Text strong>每日自评分布</Typography.Text>
      <Select aria-label="查看自评日期" value={day} onChange={select} options={days.map(value=>({label:value,value}))}/>
    </Space>
    <div className="report-center-two">
      <CountBars title="情绪分布" counts={counts(data.emotion)} labels={emotion}/>
      <CountBars title="压力分布" counts={counts(data.stress)} labels={stress}/>
    </div>
  </Space>
}

export function WellbeingBoard() {
  const {user,can}=useAuth()
  const fullSchool=can('reports:wellbeing:read')
  const canPrepare=can('student-alerts:read') && !fullSchool
  const write=can('student-alerts:write')
  const cache=useQueryClient()
  const {message}=App.useApp()
  const [anchor,setAnchor]=useState(today)
  const [draft,setDraft]=useState<Archive>()
  const [suggestion,setSuggestion]=useState('')
  const [action,setAction]=useState<ActionSpec|null>(null)
  const [activeCase,setActiveCase]=useState<number>()
  const [casePage,setCasePage]=useState(0)
  const weekly=useQuery({queryKey:[user?.id,'wellbeing-week',anchor],enabled:!!anchor,
    queryFn:()=>api<Snapshot>(staff+'/week'+query({anchor}))})
  const cases=useQuery({queryKey:[user?.id,'wellbeing-cases',casePage],enabled:write,
    queryFn:()=>api<{items:Case[];has_more:boolean}>(staff+'/cases'+query({offset:casePage}))})
  const detail=useQuery({queryKey:[user?.id,'wellbeing-case',activeCase],enabled:write&&!!activeCase,
    queryFn:()=>api<Case>(staff+'/cases/'+activeCase)})
  const calendar=useQuery({queryKey:[user?.id,'wellbeing-calendar'],enabled:can('student-alerts:read'),queryFn:()=>api<Event[]>(staff+'/calendar')})
  const students=useQuery({queryKey:[user?.id,'wellbeing-students'],enabled:write,
    queryFn:()=>api<{id:number;real_name:string}[]>('/api/v1/student-admin/psych-alerts/students')})
  const generate=useMutation({mutationFn:(include_ai:boolean)=>api<Archive>(staff+'/reports',{
    method:'POST',body:{anchor,include_ai},timeout:55000,
  }),onSuccess:row=>{
    setDraft(row)
    if(row.archive_id!==draft?.archive_id||row.ai_summary!==draft.ai_summary)setSuggestion(row.ai_summary||'')
    void cache.invalidateQueries({queryKey:[user?.id,'report-archive']})
  }})
  const publish=useMutation({mutationFn:()=>api(staff+'/reports/'+draft?.archive_id+'/review',{
    method:'POST',body:{suggestion:suggestion.trim()},
  }),onSuccess:()=>{
    setDraft(row=>row&&({...row,review_status:'published'}))
    void message.success('心理周报已发布')
    void cache.invalidateQueries({queryKey:[user?.id,'report-archive']})
  }})
  const careSuggestion=useMutation({
    mutationFn:(id:number)=>api<{suggestion:string}>(staff+'/cases/'+id+'/suggestion',{method:'POST',timeout:130000}),
    onSuccess:(result,id)=>setAction({
      title:'核验关怀建议（依据个案说明和最近十条跟进）',path:staff+'/cases/'+id+'/follow-ups',method:'POST',
      fields:[{name:'status',label:'跟进状态',kind:'select',required:true,initial:'following',options:options(caseStates)},
        {name:'note',label:'关怀计划与回访安排',kind:'textarea',required:true,initial:result.suggestion}],
    }),
  })
  const data=weekly.data
  const canDraft=!!data&&(!data.suppressed||data.items.length>0)
  const draftIsCurrent=draft&&data&&draft.period_start===data.period_start
  return <Space orientation="vertical" style={{width:'100%'}} size="middle">
    <Card><Space wrap>
      <Input aria-label="心理报告日期" type="date" value={anchor} disabled={generate.isPending||publish.isPending} onChange={event=>{setAnchor(event.target.value);setDraft(undefined)}}/>
      {canPrepare && <><Button disabled={!canDraft||generate.isPending||publish.isPending} loading={generate.isPending&&generate.variables===false} onClick={()=>generate.mutate(false)}>生成周报草稿</Button>
      <Button type="primary" disabled={!data||data.suppressed||generate.isPending||publish.isPending} loading={generate.isPending&&generate.variables===true} onClick={()=>generate.mutate(true)}>生成 AI 建议</Button></>}
    </Space>
      {data && <div className="report-center-empty-note"><Typography.Text type="secondary">
        {data.period_start} 至 {data.period_end} · {fullSchool ? '全体在读学生' : '我负责的班级'}
      </Typography.Text></div>}
      {data&&canPrepare&&!canDraft&&<div className="report-center-empty-note"><Typography.Text type="secondary">本周暂无可归档的心理统计。</Typography.Text></div>}</Card>
    <ReportHistory kind="psych_weekly"/>
    <ErrorNotice error={weekly.error||generate.error||publish.error}/>
    {data && <>
      <div className="report-center-grid">
        <Metric label="统计范围内学生" value={data.eligible}/>
        <Metric label="参与自评" value={data.suppressed?'低于展示人数':data.participants}/>
        <Metric label="自评覆盖率" value={data.eligible&&!data.suppressed?Math.round((data.participants??0)*100/data.eligible)+'%':'—'}/>
      </div>
      <DailyCheckins data={data}/>
      <WellbeingCharts data={data}/>
      <WellbeingTrend anchor={anchor}/>
    </>}
    {draftIsCurrent && <Card title={draft.review_status==='published'?'心理周报已发布':'心理周报待审核'}>
      <Space orientation="vertical" style={{width:'100%'}}>
        <Typography.Text type="secondary">{draft.period_start} 至 {draft.period_end} · 统计范围 {draft.eligible} 人 · {draft.suppressed?'自评参与人数低于展示门槛':'自评参与 '+draft.participants+' 人'} · 预警 {draft.items.reduce((sum,row)=>sum+row.count,0)} 条</Typography.Text>
        <Input.TextArea aria-label="心理周报群体建议" rows={5} value={suggestion} maxLength={4000}
          disabled={draft.review_status==='published'} onChange={event=>setSuggestion(event.target.value)}/>
        {draft.review_status!=='published' && write && <Button type="primary" loading={publish.isPending}
          disabled={!suggestion.trim()||generate.isPending} onClick={()=>publish.mutate()}>审核并发布</Button>}
      </Space>
    </Card>}
    {write && <Card title="关怀个案" extra={<Button onClick={()=>setAction({
      title:'新增关怀个案',path:staff+'/cases',method:'POST',
      fields:[{name:'student_id',label:'学生',kind:'select',required:true,
        options:students.data?.map(s=>({value:s.id,label:s.real_name}))||[]},{name:'note',label:'说明',kind:'textarea',required:true}],
    })}>新增个案</Button>}>
      <ErrorNotice error={cases.error||detail.error||careSuggestion.error}/>
      <Table<Case> rowKey="id" pagination={false} dataSource={cases.data?.items||[]} columns={[
        {title:'编号',dataIndex:'id'},{title:'学生编号',dataIndex:'student_id',width:130},{title:'姓名',dataIndex:'student_name',width:120,render:value=>value||'—'},{title:'状态',render:(_,row)=><Tag>{caseStates[row.status]}</Tag>},
        {title:'操作',render:(_,row)=><Space><Button type="link" onClick={()=>setActiveCase(row.id)}>查看</Button>
          {row.status!=='closed'&&<Button type="link" loading={careSuggestion.isPending&&careSuggestion.variables===row.id}
            onClick={()=>careSuggestion.mutate(row.id)}>生成关怀建议</Button>}
          {row.status!=='closed'&&<Button type="link" onClick={()=>setAction({
            title:'关怀跟进',path:staff+'/cases/'+row.id+'/follow-ups',method:'POST',
            fields:[{name:'status',label:'状态',kind:'select',required:true,initial:'following',options:options(caseStates)},
              {name:'note',label:'跟进记录',kind:'textarea',required:true}],
          })}>跟进</Button>}</Space>},
      ]}/>
      <Space style={{marginTop:12}}>
        <Button disabled={!casePage} onClick={()=>setCasePage(i=>i-30)}>上一页</Button>
        <Button disabled={!cases.data?.has_more} onClick={()=>setCasePage(i=>i+30)}>下一页</Button>
      </Space>
    </Card>}
    {can('student-alerts:read') && <Card title="关怀日历" extra={write&&<Button onClick={()=>setAction({
      title:'添加关怀安排',path:staff+'/calendar',method:'POST',
      fields:[{name:'title',label:'标题',required:true},{name:'day',label:'日期',kind:'date',required:true},
        {name:'note',label:'说明',kind:'textarea',required:true}],
    })}>添加安排</Button>}>
      <ErrorNotice error={calendar.error}/>
      <Table<Event> rowKey="id" pagination={false} dataSource={calendar.data||[]}
        columns={[{title:'日期',dataIndex:'day'},{title:'标题',dataIndex:'title'},{title:'说明',dataIndex:'note'}]}/>
    </Card>}
    <ActionModal action={action} onClose={()=>setAction(null)}/>
    <DetailDrawer data={activeCase?detail.data||{}:null} onClose={()=>setActiveCase(undefined)} title="关怀个案详情"/>
  </Space>
}

export function StudentWellbeing({request}:{request:Request}) {
  const cache=useQueryClient()
  const {message}=App.useApp()
  const [care]=Form.useForm<{note:string}>()
  const key=['visitor','wellbeing']
  const panel=useQuery({queryKey:key,queryFn:()=>request<Panel>(student)})
  const consent=useMutation({mutationFn:(granted:boolean)=>request(student+'/consent','PUT',{granted,version:panel.data?.version}),
    onSuccess:()=>cache.invalidateQueries({queryKey:key})})
  const checkin=useMutation({mutationFn:(values:Omit<Checkin,'day'>)=>request(student+'/check-ins','POST',values),
    onSuccess:()=>{void message.success('自评已保存');void cache.invalidateQueries({queryKey:key})}})
  const ask=useMutation({mutationFn:(values:{note:string})=>request(student+'/care','POST',values),
    onSuccess:()=>{care.resetFields();void message.success('关怀申请已提交')}})
  return <Space orientation="vertical" style={{width:'100%'}} size="middle">
    <ErrorNotice error={panel.error||consent.error||checkin.error||ask.error}/>
    <Card title="心理自评" loading={panel.isPending}>
      {panel.data&&<Space orientation="vertical" style={{width:'100%'}}>
        <Typography.Paragraph>{panel.data.description}</Typography.Paragraph>
        <Button loading={consent.isPending} onClick={()=>consent.mutate(!panel.data?.granted)}>
          {panel.data.granted?'撤回自评授权':'同意自评授权'}
        </Button>
        {panel.data.granted&&<Form layout="inline" onFinish={values=>checkin.mutate(values)}>
          <Form.Item label="今天的感受" name="emotion" rules={[{required:true}]}><Select options={options(emotion)} style={{width:130}}/></Form.Item>
          <Form.Item label="压力程度" name="stress" rules={[{required:true}]}><Select options={options(stress)} style={{width:130}}/></Form.Item>
          <Form.Item><Button type="primary" htmlType="submit" loading={checkin.isPending}>保存自评</Button></Form.Item>
        </Form>}
        <Table<Checkin> rowKey="day" size="small" pagination={false} dataSource={panel.data.checkins} columns={[
          {title:'日期',dataIndex:'day'},{title:'感受',render:(_,row)=>emotion[row.emotion]},
          {title:'压力',render:(_,row)=>stress[row.stress]},
        ]}/>
      </Space>}
    </Card>
    <Card title="申请关怀">
      <Form form={care} layout="vertical" onFinish={values=>ask.mutate(values)}>
        <Form.Item label="希望老师提供的帮助" name="note" rules={[{required:true,whitespace:true}]}><Input.TextArea maxLength={2000}/></Form.Item>
        <Button type="primary" htmlType="submit" loading={ask.isPending}>提交申请</Button>
      </Form>
    </Card>
  </Space>
}
