import {useState} from 'react'
import {App, Button, Card, Drawer, Form, Input, Select, Space, Table, Tabs, Tag, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ActionModal, ErrorNotice, DataResult, type ActionSpec} from '../components/shared'
import {api, download, query} from '../lib/api'
import {ReportSchedules} from './ReportSchedules'
import {WellbeingBoard} from './Wellbeing'
import {today} from './reportDates'
import {CountBars, Metric, statuses} from './ReportMetrics'
import './report-center.css'

const root = '/api/v1/reporting'
type Counts = Record<string,number>
type Row = {id: number; customer_name?: string; title?: string; status: string; category?: string; occurred_at?: string;create_time?: string;reason?: string;satisfaction?: number}
type Operations = {leads_by_status?: Counts;complaints_by_status?: Counts;transitions?: Counts;lost_reasons?: Counts;categories?: Counts;satisfaction?: Counts;backlog?: Counts;as_of?: string;status_history_since?: string;department: string|null;departments?: {department:string|null;new:number;signed:number;lost:number}[];items:Row[];has_more:boolean}
type Employee = {employee_id:number;name:string;department:string|null;report_days:number;submitted_at:string|null}
type Dept = {department:string|null;expected:number;submitted:number;missing:number}
type Employees = {expected:number;submitted:number;missing:number;departments:Dept[];items:Employee[];has_more:boolean}
type StaffDetail = {real_name:string;weekly_report?:{week_start:string;content:string;key_progress?:string;risks?:string;next_plan?:string};reports:{id:number;report_date:string;content:string;key_progress?:unknown;risks?:unknown;next_plan?:string}[]}

export function ReportCenter() {
  const {can} = useAuth()
  const operations = can('reports:operations:read')
  const staff = can('reports:summary:read')
  const psych = can('student-alerts:read')
  const [selected, select] = useState<string>()
  const panels = [
    ...(operations ? [{key:'customers',label:'客户经营',children:<OperationBoard kind="customers"/>},
      {key:'complaints',label:'投诉周报',children:<OperationBoard kind="complaints"/>}] : []),
    ...(staff ? [{key:'employees',label:'员工日报周报',children:<EmployeeBoard/>}] : []),
    ...(psych ? [{key:'wellbeing',label:'心理健康周报',children:<WellbeingBoard/>}] : []),
    {key:'archive',label:'计划与归档',children:<ReportSchedules/>},
  ]
  const active = panels.some(panel=>panel.key===selected) ? selected : panels[0].key
  return <div className="report-center">
    <header className="report-center-heading"><Typography.Title level={2}>智报中心</Typography.Title>
      <Button onClick={()=>window.print()}>打印当前报表</Button>
    </header>
    <div className="report-center-shortcuts">
      {panels.map(panel=><button key={panel.key} type="button" aria-pressed={active===panel.key}
        onClick={()=>select(panel.key)}>{panel.label}</button>)}
    </div>
    <Tabs activeKey={active} onChange={select} items={panels}/>
  </div>
}

function OperationBoard({kind}: {kind:'customers'|'complaints'}) {
  const {user} = useAuth()
  const {message} = App.useApp()
  const cache = useQueryClient()
  const now = today()
  const [range, setRange] = useState({start:now.slice(0,8)+'01',end:now})
  const [metric, setMetric] = useState<'new'|'signed'|'lost'|'backlog'>()
  const [offset,setOffset] = useState(0)
  const endpoint = root+'/board/'+kind
  const result = useQuery({queryKey:[user?.id,endpoint,range],queryFn:()=>api<Operations>(endpoint+query(range))})
  const detail = useQuery({queryKey:[user?.id,endpoint,range,metric,offset],enabled:!!metric,
    queryFn:()=>api<Operations>(endpoint+query({...range,metric,offset}))})
  const archive = useMutation({mutationFn:(include_ai:boolean)=>api<{archive_id:number}>(endpoint+'/archive',{method:'POST',body:{...range,include_ai},timeout:55000}),
    onSuccess: async ({archive_id})=>{
      await cache.invalidateQueries({queryKey:[user?.id,'report-archive']})
      void message.success('报表已归档')
      await download(root+'/archive/'+archive_id+'/pdf',(kind==='customers'?'客户经营报告-':'投诉处理周报-')+archive_id+'.pdf')
        .catch((error:Error)=>void message.error(error.message))
    }})
  const data=result.data
  const customer=kind==='customers'
  const counts = (customer ? data?.leads_by_status : data?.complaints_by_status) || {}
  const total = Object.values(counts).reduce((a,b)=>a+b,0)
  const historyComplete = !!data?.status_history_since && range.start>=data.status_history_since
  function open(next: NonNullable<typeof metric>) {setOffset(0);setMetric(next)}
  return <Space orientation="vertical" size="middle" style={{width:'100%'}}>
    <Card className="report-center-panel">
      <Form layout="inline" initialValues={range} onFinish={(value)=>{setRange(value);setMetric(undefined)}}>
        <Form.Item name="start" label="开始日期" rules={[{required:true}]}><Input type="date"/></Form.Item>
        <Form.Item name="end" label="结束日期" rules={[{required:true}]}><Input type="date"/></Form.Item>
        <Form.Item><Button htmlType="submit" type="primary" loading={result.isFetching}>查询</Button></Form.Item>
        <Form.Item><Space wrap>
          <Button loading={archive.isPending} onClick={()=>archive.mutate(false)}>归档并下载 PDF</Button>
          {!customer&&<Button disabled={archive.isPending} onClick={()=>archive.mutate(true)}>生成 AI 摘要并下载</Button>}
        </Space></Form.Item>
      </Form>
      <ErrorNotice error={result.error || archive.error}/>
    </Card>
    {data && <>
      <Typography.Text type="secondary">范围 · {data.department || '全公司'}</Typography.Text>
      <div className="report-center-grid">
        <Metric label={customer?'周期新增线索':'周期新增投诉'} value={total} drill={()=>open('new')}/>
        {customer ? <>
          <Metric label="周期签约" value={historyComplete?(data.transitions?.signed||0):'数据不足'} drill={()=>open('signed')}/>
          <Metric label="周期流失" value={historyComplete?(data.transitions?.lost||0):'数据不足'} drill={()=>open('lost')}/>
        </> : <Metric label="当前待处理积压" value={Object.values(data.backlog||{}).reduce((a,b)=>a+b,0)} drill={()=>open('backlog')}/>}
      </div>
      {customer && !historyComplete && <Typography.Text type="secondary">实际签约和流失时间自 {data.status_history_since || '记录启用日'} 起完整统计。</Typography.Text>}
      {!customer && data.as_of && <Typography.Text type="secondary">积压按当前状态统计，截至 {data.as_of.replace('T',' ')}。</Typography.Text>}
      <div className="report-center-two">
        <CountBars title={customer?'线索状态':'投诉状态'} counts={counts}/>
        <CountBars title={customer?'已记录的流失原因':'投诉分类'} counts={(customer?data.lost_reasons:data.categories)||{}}/>
        {!customer && <>
          <CountBars title="积压账龄" counts={data.backlog||{}}/>
          <CountBars title="满意度分布" counts={data.satisfaction||{}}/>
        </>}
      </div>
      {customer && <Card title="分部门经营数据">
        <Table rowKey={row=>row.department||''} pagination={false} dataSource={data.departments||[]} columns={[
          {title:'部门',render:(_,row)=>row.department||'未填写部门'},
          {title:'新增线索',dataIndex:'new'},
          {title:'已记录签约',render:(_,row)=>historyComplete?row.signed:'—'},
          {title:'已记录流失',render:(_,row)=>historyComplete?row.lost:'—'},
        ]}/>
      </Card>}
    </>}
    <Drawer open={!!metric} onClose={()=>setMetric(undefined)} size="large" title={
      metric==='backlog'?'当前投诉积压':metric==='signed'?'签约记录':metric==='lost'?'流失记录':customer?'新增线索':'新增投诉'}>
      <ErrorNotice error={detail.error}/>
      <Table<Row> rowKey="id" loading={detail.isFetching} dataSource={detail.data?.items||[]} pagination={false}
        columns={[{title:'编号',dataIndex:'id'},{title:'标题',render:(_,row)=>row.customer_name||row.title||'—'},
          {title:'状态',render:(_,row)=>statuses[row.status]||row.status},
          {title:'时间',render:(_,row)=>(row.occurred_at||row.create_time||'').replace('T',' ')},
          {title:customer?'原因':'分类',render:(_,row)=>row.reason||row.category||'—'}]}/>
      <Pages offset={offset} more={detail.data?.has_more} move={setOffset}/>
    </Drawer>
  </Space>
}

function Pages({offset,more,move}:{offset:number;more?:boolean;move:(n:number)=>void}) {
  return <Space style={{marginTop:12}}>
    <Button disabled={!offset} onClick={()=>move(Math.max(0,offset-30))}>上一页</Button>
    <Button disabled={!more} onClick={()=>move(offset+30)}>下一页</Button>
  </Space>
}

function EmployeeBoard() {
  const {user,can}=useAuth()
  const cache=useQueryClient()
  const {message}=App.useApp()
  const [anchor,setAnchor]=useState(today)
  const [period,setPeriod]=useState<'day'|'week'>('day')
  const [department,setDepartment]=useState<string>()
  const [status,setStatus]=useState<string>()
  const [offset,setOffset]=useState(0)
  const [selected,setSelected]=useState<number>()
  const [report,setReport]=useState<{archive_id:number;sections:Record<string,string>}>()
  const endpoint=root+'/board/employees'
  const params={anchor,period,department,status,offset}
  const roster=useQuery({queryKey:[user?.id,endpoint,params],enabled:!!anchor,queryFn:()=>api<Employees>(endpoint+query(params))})
  const departments=useQuery({queryKey:[user?.id,endpoint,anchor,period,'departments'],enabled:!!anchor,
    queryFn:()=>api<Employees>(endpoint+query({anchor,period,limit:1}))})
  const daily=useQuery({queryKey:[user?.id,'report-submissions',anchor,period],enabled:!!anchor,
    queryFn:()=>api<{submitted_employee_days:number;days:{report_date:string;submitted_employees:number}[]}>(
      root+'/employee-reports/summary'+query({anchor,period}))})
  const employee=useQuery({queryKey:[user?.id,endpoint,selected,anchor,period],enabled:!!selected&&!!anchor,
    queryFn:()=>api<StaffDetail>(endpoint+'/'+selected+query({anchor,period}))})
  const generate=useMutation({mutationFn:()=>api<{archive_id:number;sections:Record<string,string>}>(root+'/employee-reports/formal-summary',{
    method:'POST',body:{anchor,report_kind:period==='day'?'daily':'weekly'},timeout:130000,
  }),onSuccess:result=>{setReport(result);void cache.invalidateQueries({queryKey:[user?.id,'report-archive']})}})
  const row=roster.data
  const sectionNames:Record<string,string>={work_summary:'工作总结',key_progress_summary:'关键进展',risk_summary:'风险事项',next_work_suggestions:'下一步建议'}
  return <Space orientation="vertical" size="middle" style={{width:'100%'}}>
    <Card><Space wrap>
      <Input aria-label="统计日期" type="date" value={anchor} onChange={e=>{setAnchor(e.target.value);setOffset(0);setReport(undefined)}}/>
      <Select aria-label="统计周期" value={period} options={[{label:'员工日报',value:'day'},{label:'员工周报',value:'week'}]} onChange={v=>{setPeriod(v);setOffset(0);setReport(undefined)}}/>
      <Select allowClear placeholder="全部部门" aria-label="部门" value={department} style={{minWidth:135}}
        options={departments.data?.departments.flatMap(d=>d.department?[{value:d.department,label:d.department}]:[])}
        onChange={v=>{setDepartment(v);setOffset(0)}}/>
      <Select allowClear placeholder="提交状态" aria-label="提交状态" value={status} style={{minWidth:135}}
        options={[{value:'submitted',label:'已提交'},{value:'missing',label:'未提交'}]} onChange={v=>{setStatus(v);setOffset(0)}}/>
      {can('reports:formal:generate') && <Button type="primary" loading={generate.isPending} disabled={!anchor}
        onClick={()=>generate.mutate()}>生成并归档 AI 报告</Button>}
    </Space><ErrorNotice error={roster.error||generate.error}/></Card>
    {row && <>
      <div className="report-center-grid">
        <Metric label="应提交" value={row.expected}/><Metric label="已提交" value={row.submitted}/>
        <Metric label="未提交" value={row.missing}/><Metric label="提交率" value={row.expected?Math.round(row.submitted/row.expected*100)+'%':'—'}/>
      </div>
      {daily.data&&<CountBars title={'日报提交趋势 · 累计 '+daily.data.submitted_employee_days+' 人次'}
        counts={Object.fromEntries(daily.data.days.map(day=>[day.report_date,day.submitted_employees]))}/>}
      <Card title="各部门提交情况">
        <Table<Dept> rowKey={row=>row.department||''} size="small" pagination={false} dataSource={row.departments} columns={[
          {title:'部门',render:(_,d)=>d.department||'未填写部门'},{title:'应提交',dataIndex:'expected'},
          {title:'已提交',dataIndex:'submitted'},{title:'未提交',dataIndex:'missing'},
          {title:'提交率',render:(_,d)=>d.expected?Math.round(d.submitted/d.expected*100)+'%':'—'},
        ]}/>
      </Card>
      <Card title="员工提交名单">
        <Table<Employee> rowKey="employee_id" size="small" pagination={false} dataSource={row.items} columns={[
          {title:'员工',dataIndex:'name'},{title:'部门',dataIndex:'department'},
          {title:'提交状态',render:(_,e)=><Tag color={e.report_days?'green':undefined}>{e.report_days?'已提交':'未提交'}</Tag>},
          {title:period==='day'?'提交天数':'本周提交',render:(_,e)=>period==='day'?e.report_days:e.report_days?'已交周报':'未交周报'},{title:'操作',render:(_,e)=><Button type="link" onClick={()=>setSelected(e.employee_id)}>查看详情</Button>},
        ]}/>
        <Pages offset={offset} more={row.has_more} move={setOffset}/>
      </Card>
    </>}
    {report && <Card title="已归档的正式 AI 报告" extra={<Button onClick={()=>void download(root+'/archive/'+report.archive_id+'/pdf','正式报告-'+report.archive_id+'.pdf').catch((error:Error)=>void message.error(error.message))}>下载 PDF</Button>}>
      {Object.entries(report.sections).map(([key,value])=><section key={key}>
        <Typography.Title level={5}>{sectionNames[key]}</Typography.Title><Typography.Paragraph style={{whiteSpace:'pre-wrap'}}>{value}</Typography.Paragraph>
      </section>)}
    </Card>}
    <Drawer title={employee.data?.real_name||'员工日报'} onClose={()=>setSelected(undefined)} open={!!selected} size="large">
      <DataResult data={employee.data?.weekly_report?{周报起始:employee.data.weekly_report.week_start,工作总结:employee.data.weekly_report.content,关键进展:employee.data.weekly_report.key_progress,风险事项:employee.data.weekly_report.risks,下一步:employee.data.weekly_report.next_plan}:employee.data?.reports.map(x=>({日期:x.report_date,工作总结:x.content,关键进展:x.key_progress,风险事项:x.risks,下一步:x.next_plan}))||[]}/>
      {selected && anchor && period==='week' && <EmployeeConflicts employee={selected} anchor={anchor}/>}
    </Drawer>
    <ErrorNotice error={employee.error}/>
  </Space>
}

type Finding = {id:number;summary:string;daily_excerpt:string;weekly_excerpt:string;status:string;verify_note?:string}

function EmployeeConflicts({employee,anchor}:{employee:number;anchor:string}) {
  const {user,can}=useAuth()
  const cache=useQueryClient()
  const [action,setAction]=useState<ActionSpec|null>(null)
  const path=root+'/board/employees/'+employee+'/conflicts'+query({anchor})
  const key=[user?.id,'report-conflicts',employee,anchor]
  const rows=useQuery({queryKey:key,queryFn:()=>api<Finding[]>(path)})
  const scan=useMutation({mutationFn:()=>api<Finding[]>(path,{method:'POST',timeout:55000}),
    onSuccess:value=>cache.setQueryData(key,value)})
  const manage=can('reports:formal:generate')
  return <Card size="small" title="日报与周报冲突事项" extra={manage&&
    <Button loading={scan.isPending} onClick={()=>scan.mutate()}>运行 AI 比对</Button>}>
    <ErrorNotice error={rows.error||scan.error}/>
    {rows.data?.length===0&&<Typography.Text type="secondary">暂无比对记录</Typography.Text>}
    {rows.data?.map(row=><div key={row.id} style={{marginBottom:16}}>
      <Space><Typography.Text strong>{row.summary}</Typography.Text>
        <Tag>{row.status==='pending'?'待核验':row.status==='verified'?'已核验':'已忽略'}</Tag></Space>
      <Typography.Paragraph>日报 · {row.daily_excerpt}<br/>周报 · {row.weekly_excerpt}</Typography.Paragraph>
      {row.verify_note&&<Typography.Paragraph>{row.verify_note}</Typography.Paragraph>}
      {manage&&row.status==='pending'&&<Button onClick={()=>setAction({
        title:'核验冲突事项',method:'PUT',path:root+'/board/conflicts/'+row.id,
        fields:[{name:'status',label:'核验结果',kind:'select',required:true,options:[{value:'verified',label:'确认冲突'},{value:'dismissed',label:'忽略'}]},
          {name:'verify_note',label:'核验说明',kind:'textarea',required:true}],
      })}>核验</Button>}
    </div>)}
    <ActionModal action={action} onClose={()=>setAction(null)}/>
  </Card>
}
