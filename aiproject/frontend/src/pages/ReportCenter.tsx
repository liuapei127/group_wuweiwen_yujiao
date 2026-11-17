import {useState} from 'react'
import {App, Button, Card, Checkbox, Drawer, Form, Input, Select, Space, Table, Tag, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ErrorNotice} from '../components/shared'
import {api, download, query} from '../lib/api'
import {ReportSchedules} from './ReportSchedules'
import {ReportHistory} from './ReportHistory'
import {OperationAnalysis, useOperationAnalysis, ProjectHealth} from './ReportAnalysis'
import {EmployeeReportReader, type StaffDetail} from './EmployeeReportReader'
import {WellbeingBoard} from './Wellbeing'
import {today} from './reportDates'
import {Metric, statuses} from './ReportMetrics'
import {CustomerFeatureCharts, DepartmentChart, DistributionChart} from './ReportCharts'
import './report-center.css'

const root = '/api/v1/reporting'
type Counts = Record<string,number>
type Row = {id:number;record_id?:number;customer_name?:string;title?:string;status:string;category?:string;occurred_at?:string;
  create_time?:string;reason?:string;satisfaction?:number;follow_type?:string;source_channel?:string;intended_country?:string;education_level?:string;intended_project?:string}
type Comparison = {start:string;end:string;count:number;change:number;percent:number|null}
type Operations = {leads_by_status?:Counts;complaints_by_status?:Counts;transitions?:Counts;lost_reasons?:Counts;
  follow_ups?:Counts;source_channels?:Counts;categories?:Counts;satisfaction?:Counts;backlog?:Counts;as_of?:string;
  status_history_since?:string;department:string|null;departments?:{department:string|null;new:number;signed:number;lost:number}[];
  comparisons?:{previous?:Comparison;year_ago?:Comparison};items:Row[];has_more:boolean}
type OperationDetail = {title:string;metric:'new'|'signed'|'lost'|'backlog'|'status'|'channel'|'follow_up'|'category'|'satisfaction'|'country'|'education'|'project';
  bucket?:string;department?:string;department_missing?:boolean}
const followLabels:Record<string,string>={phone:'电话',wechat:'微信',meeting:'面谈',email:'邮件',other:'其他'}
const countSum=(counts:Counts)=>Object.values(counts).reduce((a,b)=>a+b,0)
type Employee = {employee_id:number;name:string;department:string|null;report_days:number;submitted_at:string|null}
type Dept = {department:string|null;expected:number;submitted:number;missing:number}
type Employees = {expected:number;submitted:number;missing:number;departments:Dept[];items:Employee[];has_more:boolean}

export function ReportCenter() {
  const {can} = useAuth()
  const operations = can('reports:operations:read')
  const staff = can('reports:summary:read')
  const psych = can('student-alerts:read') || can('reports:wellbeing:read')
  const [selected, select] = useState<string>()
  const [visited, setVisited] = useState<string[]>([])
  const panels = [
    ...(operations ? [{key:'customers',label:'客户经营',children:<OperationBoard kind="customers"/>},
      {key:'complaints',label:'投诉周报',children:<OperationBoard kind="complaints"/>}] : []),
    ...(staff ? [{key:'employees',label:'员工日报周报',children:<EmployeeBoard/>}] : []),
    ...(psych ? [{key:'wellbeing',label:'心理健康周报',children:<WellbeingBoard/>}] : []),
    {key:'archive',label:'计划与归档',children:<ReportSchedules/>},
  ]
  const active = panels.find(panel=>panel.key===selected)?.key??panels[0].key
  return <div className="report-center">
    <header className="report-center-heading"><Typography.Title level={2}>智报中心</Typography.Title>
      <Button onClick={()=>window.print()}>打印当前报表</Button>
    </header>
    <nav className="report-center-shortcuts" aria-label="智报分类">
      {panels.map(panel=><button key={panel.key} type="button" aria-pressed={active===panel.key}
        id={'report-nav-'+panel.key} aria-controls={'report-panel-'+panel.key}
        onClick={()=>{setVisited(keys=>keys.includes(active)?keys:[...keys,active]);select(panel.key)}}>{panel.label}</button>)}
    </nav>
    {panels.map(panel=><section key={panel.key} id={'report-panel-'+panel.key} aria-labelledby={'report-nav-'+panel.key}
      hidden={active!==panel.key}>{(active===panel.key||visited.includes(panel.key))&&panel.children}</section>)}
  </div>
}

function OperationBoard({kind}: {kind:'customers'|'complaints'}) {
  const {user}=useAuth()
  const {message}=App.useApp()
  const cache=useQueryClient()
  const now=today()
  const [range,setRange]=useState({start:now.slice(0,8)+'01',end:now})
  const [rangeForm]=Form.useForm()
  const [selection,setSelection]=useState<OperationDetail>()
  const [offset,setOffset]=useState(0)
  const [includeAI,setIncludeAI]=useState(false)
  const [generated,setGenerated]=useState<{archive_id:number;ai_summary?:string}>()
  const [downloading,setDownloading]=useState(false)
  const endpoint=root+'/board/'+kind
  const customer=kind==='customers'
  const result=useQuery({queryKey:[user?.id,endpoint,range],queryFn:()=>api<Operations>(endpoint+query(range))})
  const analysis=useOperationAnalysis(kind,range.start,range.end,customer)
  const detail=useQuery({queryKey:[user?.id,endpoint,range,selection,offset],enabled:!!selection,
    queryFn:()=>api<Operations>(endpoint+query({...range,metric:selection?.metric,bucket:selection?.bucket,
      department:selection?.department,department_missing:selection?.department_missing,offset}))})
  const archive=useMutation({mutationFn:(body:{start:string;end:string;include_ai:boolean})=>
    api<{archive_id:number;ai_summary?:string}>(endpoint+'/archive',{method:'POST',body,timeout:130000}),
    onMutate:()=>setGenerated(undefined),
    onSuccess:report=>{
      setGenerated(report)
      void cache.invalidateQueries({queryKey:[user?.id,'report-archive']})
      void message.success('报告已生成，可点击下载 PDF')
    }})
  async function generateReport() {
    try {
      const value=await rangeForm.validateFields()
      setRange(value);setSelection(undefined)
      archive.mutate({...value,include_ai:!customer&&includeAI})
    } catch { /* Form validation displays field errors. */ }
  }
  async function downloadReport() {
    if(!generated)return
    setDownloading(true)
    try {await download(root+'/archive/'+generated.archive_id+'/pdf',(customer?'客户经营报告-':'投诉处理周报-')+generated.archive_id+'.pdf')}
    catch(error){void message.error((error as Error).message)}
    finally {setDownloading(false)}
  }
  const data=result.data
  const counts=(customer?data?.leads_by_status:data?.complaints_by_status)||{}
  const total=countSum(counts)
  const historyComplete=!!data?.status_history_since&&range.start>=data.status_history_since
  const signedLabel=historyComplete?'周期签约':'已记录签约'
  const lostLabel=historyComplete?'周期流失':'已记录流失'
  function open(metric:OperationDetail['metric'],title:string,filters:Omit<OperationDetail,'metric'|'title'>={}) {
    setOffset(0);setSelection({metric,title,...filters})
  }
  function openDepartment(department:string|null,metric:'new'|'signed'|'lost') {
    const label=department||'未填写部门'
    const title=metric==='new'?'新增线索':metric==='signed'?'签约记录':'流失记录'
    open(metric,label+' · '+title,department===null?{department_missing:true}:{department})
  }
  function departmentCount(department:string|null,metric:'new'|'signed'|'lost',value:number) {
    return value>0?<Button type="link" className="report-center-table-link" onClick={()=>openDepartment(department,metric)}>{value}</Button>:value
  }
  const comparisons=customer?analysis.data?.comparisons:data?.comparisons
  return <Space orientation="vertical" size="middle" style={{width:'100%'}}>
    <Card className="report-center-panel report-filter-panel">
      <Form form={rangeForm} layout="inline" initialValues={range} disabled={archive.isPending||downloading}
        onValuesChange={()=>setGenerated(undefined)} onFinish={value=>{setRange(value);setSelection(undefined);setGenerated(undefined)}}>
        <Form.Item name="start" label="开始日期" rules={[{required:true}]}><Input type="date"/></Form.Item>
        <Form.Item name="end" label="结束日期" rules={[{required:true}]}><Input type="date"/></Form.Item>
        <Form.Item><Button htmlType="submit" type="primary" loading={result.isFetching}>查询</Button></Form.Item>
        <Form.Item><Space wrap>
          {!customer&&<Checkbox checked={includeAI} onChange={event=>{setIncludeAI(event.target.checked);setGenerated(undefined)}}>包含 AI 摘要</Checkbox>}
          <Button loading={archive.isPending} onClick={()=>void generateReport()}>生成报告</Button>
          <Button disabled={!generated||archive.isPending} loading={downloading} onClick={()=>void downloadReport()}>下载 PDF</Button>
        </Space></Form.Item>
      </Form>
      <ErrorNotice error={result.error||archive.error||analysis.error}/>
    </Card>
    {data&&<>
      <Typography.Text type="secondary">范围 · {data.department||'全公司'}</Typography.Text>
      <div className="report-center-grid">
        <Metric label={customer?'周期新增线索':'周期新增投诉'} value={total} drill={()=>open('new',customer?'新增线索':'新增投诉')}/>
        {customer?<>
          <Metric label={signedLabel} value={data.transitions?.signed||0} drill={()=>open('signed','签约记录')}/>
          <Metric label={lostLabel} value={data.transitions?.lost||0} drill={()=>open('lost','流失记录')}/>
        </>:<Metric label="当前待处理积压" value={countSum(data.backlog||{})} drill={()=>open('backlog','当前投诉积压')}/>}
        {comparisons?.previous&&<ComparisonCard label="较上一周期" value={comparisons.previous}/>}
        {comparisons?.year_ago&&<ComparisonCard label="较去年同期" value={comparisons.year_ago}/>}
      </div>
      {customer&&<Typography.Text type="secondary">新增线索当前状态按本期新增客户统计；签约和流失按本期状态变更记录统计。
        {!historyComplete&&(data.status_history_since?' 历史自 '+data.status_history_since+' 起完整，之前仅显示已记录数量。':' 所选周期仅显示已记录的签约和流失数量。')}
      </Typography.Text>}
      {!customer&&data.as_of&&<Typography.Text type="secondary">积压按当前状态统计，截至 {data.as_of.replace('T',' ')}。</Typography.Text>}
      <div className="report-center-two">
        <DistributionChart title={customer?'新增线索当前状态':'投诉状态'} counts={counts} variant={customer?'horizontal':'donut'}
          drill={bucket=>open('status',statuses[bucket]||bucket,{bucket})}/>
        {customer?<DistributionChart title="已记录的流失原因" counts={data.lost_reasons||{}} labels={{}}
          drill={bucket=>open('lost','流失原因 · '+bucket,{bucket})}/>:<>
          <DistributionChart title="投诉分类" counts={data.categories||{}} labels={{}} drill={bucket=>open('category','投诉分类 · '+bucket,{bucket})}/>
          <DistributionChart title="积压账龄" counts={data.backlog||{}} variant="columns" order={['0–2 天','3–6 天','7–13 天','14 天以上']}
            drill={bucket=>open('backlog','积压账龄 · '+bucket,{bucket})}/>
          <DistributionChart title="满意度分布" counts={data.satisfaction||{}} variant="columns" order={['1','2','3','4','5']}
            labels={{'1':'1 分','2':'2 分','3':'3 分','4':'4 分','5':'5 分'}}
            summary={'有效评分 '+countSum(data.satisfaction||{})+' 条'} drill={bucket=>open('satisfaction','满意度 · '+bucket+' 分',{bucket})}/>
        </>}
      </div>
      {customer&&<>
        {analysis.data?.groups&&<CustomerFeatureCharts groups={analysis.data.groups} onDrill={(metric,bucket)=>open(metric,'客户分组 · '+bucket,{bucket})}/>}
        <DepartmentChart rows={data.departments||[]} onDrill={openDepartment}/>
        <DistributionChart title="客户跟进分析" counts={data.follow_ups||{}} labels={followLabels}
          summary={'周期内记录 '+countSum(data.follow_ups||{})+' 次跟进'} drill={bucket=>open('follow_up','跟进方式 · '+(followLabels[bucket]||bucket),{bucket})}/>
        {!!data.departments?.length&&<Card title="分部门经营明细"><Table rowKey={row=>row.department??'missing'} pagination={false} scroll={{x:500}}
          dataSource={data.departments} columns={[
            {title:'部门',render:(_,row)=>row.department||'未填写部门'},
            {title:'新增线索',render:(_,row)=>departmentCount(row.department,'new',row.new)},
            {title:'已记录签约',render:(_,row)=>departmentCount(row.department,'signed',row.signed)},
            {title:'已记录流失',render:(_,row)=>departmentCount(row.department,'lost',row.lost)},
          ]}/></Card>}
      </>}
    </>}
    {!customer&&<OperationAnalysis kind={kind} start={range.start} end={range.end}/>}
    {generated?.ai_summary&&<Card title="报告摘要"><Typography.Paragraph style={{whiteSpace:'pre-wrap'}}>{generated.ai_summary}</Typography.Paragraph></Card>}
    <ReportHistory kind={customer?'customer_ops':'complaint_weekly'}/>
    <Drawer open={!!selection} onClose={()=>setSelection(undefined)} size="large" title={selection?.title}>
      <ErrorNotice error={detail.error}/>
      <Table<Row> rowKey={row=>row.record_id??row.id} loading={detail.isFetching} dataSource={detail.data?.items||[]} pagination={false}
        columns={[{title:'编号',dataIndex:'id'},{title:customer?'客户':'投诉',render:(_,row)=>row.customer_name||row.title||'—'},
          {title:'状态',render:(_,row)=>statuses[row.status]||row.status},
          ...(['country','education','project'].includes(selection?.metric||'')?[{title:'客户特征',render:(_:unknown,row:Row)=>[row.intended_country,row.education_level,row.intended_project].filter(Boolean).join(' · ')}]:[]),
          {title:'时间（北京时间）',render:(_,row)=>(row.occurred_at||row.create_time||'').replace('T',' ')},
          ...(selection?.metric==='follow_up'?[{title:'跟进方式',render:(_:unknown,row:Row)=>followLabels[row.follow_type||'']||row.follow_type||'—'}]:
            customer?[{title:'渠道 / 原因',render:(_:unknown,row:Row)=>[row.source_channel,row.reason].filter(Boolean).join(' · ')||'—'}]:
              [{title:'分类',render:(_:unknown,row:Row)=>row.category?.trim()||'未分类'},
               {title:'满意度',render:(_:unknown,row:Row)=>row.satisfaction??'—'}]),
        ]}/>
      <Pages offset={offset} more={detail.data?.has_more} move={setOffset}/>
    </Drawer>
  </Space>
}

function ComparisonCard({label,value}:{label:string;value:Comparison}) {
  const signed=(count:number)=>(count>0?'+':'')+count
  return <Card className="report-center-metric" size="small">
    <Typography.Text type="secondary">{label}</Typography.Text>
    <strong>{value.percent===null?'无可比基数':signed(value.percent)+'%'}</strong>
    <Typography.Text type="secondary">对比期 {value.count} 条 · 变化 {signed(value.change)} 条</Typography.Text>
    <div><Typography.Text type="secondary">{value.start} 至 {value.end}</Typography.Text></div>
  </Card>
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
  const employee=useQuery({queryKey:[user?.id,endpoint,selected,anchor,period],enabled:!!selected&&!!anchor,
    queryFn:()=>api<StaffDetail>(endpoint+'/'+selected+query({anchor,period}))})
  const generate=useMutation({mutationFn:()=>api<{archive_id:number;sections:Record<string,string>}>(root+'/employee-reports/formal-summary',{
    method:'POST',body:{anchor,report_kind:period==='day'?'daily':'weekly'},timeout:130000,
  }),onSuccess:result=>{setReport(result);void cache.invalidateQueries({queryKey:[user?.id,'report-archive']})}})
  const row=roster.data
  const sectionNames:Record<string,string>={work_summary:'工作总结',key_progress_summary:'关键进展',risk_summary:'风险事项',next_work_suggestions:'下一步建议'}
  return <Space orientation="vertical" size="middle" style={{width:'100%'}}>
    <Card className="report-filter-panel"><Space wrap>
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
      <Card title="各部门提交情况">
        <Table<Dept> rowKey={row=>row.department||''} size="small" pagination={false} dataSource={row.departments} columns={[
          {title:'部门',render:(_,d)=>d.department||'未填写部门'},{title:'应提交',dataIndex:'expected'},
          {title:'已提交',dataIndex:'submitted'},{title:'未提交',dataIndex:'missing'},
          {title:'提交率',render:(_,d)=>d.expected?Math.round(d.submitted/d.expected*100)+'%':'—'},
        ]}/>
      </Card>
      <Card title="员工提交名单">
        <Table<Employee> rowKey="employee_id" size="small" pagination={false} dataSource={row.items} columns={[
          {title:'员工编号',dataIndex:'employee_id'},
          {title:'员工',dataIndex:'name'},{title:'部门',dataIndex:'department'},
          {title:'提交状态',render:(_,e)=><Tag color={e.report_days?'green':undefined}>{e.report_days?'已提交':'未提交'}</Tag>},
          {title:period==='day'?'提交天数':'本周提交',render:(_,e)=>period==='day'?e.report_days:e.report_days?'已交周报':'未交周报'},{title:'操作',render:(_,e)=><Button type="link" onClick={()=>setSelected(e.employee_id)}>查看详情</Button>},
        ]}/>
        <Pages offset={offset} more={row.has_more} move={setOffset}/>
      </Card>
    </>}
    <ProjectHealth/>
    <ReportHistory kind={period === 'day' ? 'daily_summary' : 'weekly_summary'}/>
    {report && <Card title="已归档的正式 AI 报告" extra={<Button onClick={()=>void download(root+'/archive/'+report.archive_id+'/pdf','正式报告-'+report.archive_id+'.pdf').catch((error:Error)=>void message.error(error.message))}>下载 PDF</Button>}>
      {Object.entries(report.sections).map(([key,value])=><section key={key}>
        <Typography.Title level={5}>{sectionNames[key]}</Typography.Title><Typography.Paragraph style={{whiteSpace:'pre-wrap'}}>{value}</Typography.Paragraph>
      </section>)}
    </Card>}
    <Drawer title={employee.data?.real_name||'员工日报'} onClose={()=>setSelected(undefined)} open={!!selected} size="large">
      {selected && <EmployeeReportReader key={selected+'-'+anchor+'-'+period}
        employeeId={selected} period={period} detail={employee.data}
        loading={employee.isFetching} error={employee.error}/>}
    </Drawer>
    <ErrorNotice error={employee.error}/>
  </Space>
}
