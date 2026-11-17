import {Button, Card, Space, Table, Typography} from 'antd'
import {useMutation, useQuery} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ErrorNotice} from '../components/shared'
import {api, query} from '../lib/api'
import {CountBars} from './ReportMetrics'

type Comparison = {start:string;end:string;count:number;change:number;percent:number|null}
type Group = {label:string;count:number;signed:number;signed_percent:number}
type Timing = {samples:number;average_hours:number|null}
type Result = {comparisons?:Record<string,Comparison>;groups?:Record<string,Group[]>;
  first_response?:Timing;resolution?:Timing;note?:string;overdue_days?:number|null;resolution_overdue_percent?:number|null;late_resolutions?:number|null}

export function OperationAnalysis({kind,start,end}:{kind:'customers'|'complaints';start:string;end:string}) {
  const {user}=useAuth()
  const result=useQuery({queryKey:[user?.id,'report-analysis',kind,start,end],
    queryFn:()=>api<Result>('/api/v1/reporting/board/'+kind+'/analysis'+query({start,end})),
    enabled:!!start&&!!end})
  const labels:Record<string,string>={intended_country:'意向国家',education_level:'学历',intended_project:'意向项目',source_channel:'来源渠道'}
  return <Card title={kind==='customers'?'客户经营深入分析':'投诉处理时效'} loading={result.isPending}>
    <ErrorNotice error={result.error}/>
    {result.data?.comparisons&&<Table rowKey="label" size="small" pagination={false}
      dataSource={Object.entries(result.data.comparisons).map(([key,row])=>({...row,label:key==='previous'?'较上一周期':'较去年同期'}))}
      columns={[{title:'比较',dataIndex:'label'},{title:'对比期间',render:(_,row)=>row.start+' 至 '+row.end},
        {title:'新增客户数',dataIndex:'count'},{title:'变化数量',dataIndex:'change'},
        {title:'变化率',render:(_,row)=>row.percent===null?'无可比基数':row.percent+'%'}]}/>}
    {result.data?.groups&&<Space orientation="vertical" style={{width:'100%'}}>
      <Typography.Paragraph type="secondary">按所选期间新增客户的已录入特征分群；签约占比按该批客户当前状态统计。</Typography.Paragraph>
      {Object.entries(result.data.groups).map(([key,rows])=><section key={key}>
        <Typography.Title level={5}>{labels[key]}</Typography.Title>
        <Table rowKey="label" size="small" dataSource={rows} pagination={{pageSize:5,showSizeChanger:false,hideOnSinglePage:true}}
          columns={[{title:'特征分组',dataIndex:'label'},{title:'客户数',dataIndex:'count'},{title:'已签约',dataIndex:'signed'},
            {title:'签约占比',render:(_,row)=>row.signed_percent+'%'}]}/>
      </section>)}
    </Space>}
    {result.data?.first_response&&<div className="report-center-two">
      {([['首次响应',result.data.first_response],['首次解决',result.data.resolution]] as const).map(([label,value])=><Card key={label} size="small">
        <Typography.Text strong>{label}平均耗时</Typography.Text>
        <Typography.Title level={3}>{value?.average_hours===null?'暂无样本':value?.average_hours+' 小时'}</Typography.Title>
        <Typography.Text type="secondary">有效样本 {value?.samples} 条</Typography.Text>
      </Card>)}
    </div>}
    {result.data?.note&&<Typography.Paragraph type="secondary">{result.data.note}</Typography.Paragraph>}
    {kind==='complaints'&&result.data&&<Typography.Paragraph type="secondary">
      {result.data.overdue_days===null?'尚未设置投诉超时标准':
        '超时标准 '+result.data.overdue_days+' 天；已记录解决样本中超时 '+(result.data.late_resolutions??0)+' 条，超时率 '+
        (result.data.resolution_overdue_percent===null?'暂无样本':result.data.resolution_overdue_percent+'%')}
    </Typography.Paragraph>}
  </Card>
}

type Week = {period_start:string;period_end:string;eligible:number;participants:number|null;suppressed:boolean;
  items:{risk_level:string;count:number}[]}
export function WellbeingTrend({anchor}:{anchor:string}) {
  const {user}=useAuth()
  const result=useQuery({queryKey:[user?.id,'wellbeing-trend',anchor],enabled:!!anchor,
    queryFn:()=>api<{weeks:Week[]}>('/api/v1/reporting/wellbeing/trend'+query({anchor}))})
  return <Card title="近八周心理健康趋势" loading={result.isPending}>
    <ErrorNotice error={result.error}/>
    <Typography.Paragraph type="secondary">各周均按当前可查看的学生范围统计。自评参与人数沿用现有展示门槛。</Typography.Paragraph>
    <Table<Week> rowKey="period_start" dataSource={result.data?.weeks||[]} pagination={false} size="small" scroll={{x:650}}
      columns={[{title:'周报期间',render:(_,row)=>row.period_start+' 至 '+row.period_end},
        {title:'参与自评',render:(_,row)=>row.suppressed?'低于展示人数':row.participants},
        {title:'覆盖率',render:(_,row)=>row.suppressed||!row.eligible?'—':Math.round((row.participants||0)/row.eligible*100)+'%'},
        {title:'新增预警',render:(_,row)=>row.items.reduce((sum,item)=>sum+item.count,0)},
        {title:'高风险预警',render:(_,row)=>row.items.filter(item=>item.risk_level==='high').reduce((sum,item)=>sum+item.count,0)}]}/>
  </Card>
}

type Intelligence = {
  clusters:{group:number;count:number;average_age:number;average_match_score:number;average_inactive_days:number}[]
  cluster_samples:number;cluster_excluded:number;cluster_method:string
  paths:{path:string;count:number}[];unrecorded_paths:number
  high_value:{threshold:number|null;count:number;countries:Record<string,number>;education:Record<string,number>}
  inactive:{days:number|null;count:number;items:{id:number;days:number}[]}
}
export function CustomerIntelligence({start,end}:{start:string;end:string}) {
  const {user}=useAuth()
  const result=useQuery({queryKey:[user?.id,'customer-intelligence',start,end],
    queryFn:()=>api<Intelligence>('/api/v1/reporting/board/customers/intelligence'+query({start,end})),enabled:!!start&&!!end})
  const summary=useMutation({mutationFn:()=>api<{summary:string}>('/api/v1/reporting/board/customers/summary',{
    method:'POST',body:{start,end},timeout:130000})})
  const data=result.data
  const labels:Record<string,string>={new:'新线索',contacting:'联系中',qualified:'已确认意向',signed:'已签约',lost:'已流失'}
  return <Card title="客户特征聚类与风险提示" loading={result.isPending}
    extra={<Button onClick={()=>summary.mutate()} loading={summary.isPending}>生成 AI 经营摘要</Button>}>
    <ErrorNotice error={result.error||summary.error}/>
    {summary.data&&<Typography.Paragraph style={{whiteSpace:'pre-wrap'}}>{summary.data.summary}</Typography.Paragraph>}
    {data&&<Space orientation="vertical" style={{width:'100%'}} size="middle">
      <Typography.Paragraph type="secondary">{data.cluster_method} 参与 {data.cluster_samples} 名，缺少有效特征 {data.cluster_excluded} 名。</Typography.Paragraph>
      <Table rowKey="group" dataSource={data.clusters} pagination={false} size="small" scroll={{x:650}}
        columns={[{title:'特征群',dataIndex:'group'},{title:'客户数',dataIndex:'count'},{title:'平均年龄',dataIndex:'average_age'},
          {title:'平均匹配度',dataIndex:'average_match_score'},{title:'平均未联系天数',dataIndex:'average_inactive_days'}]}/>
      <Typography.Title level={5}>已记录的转化路径</Typography.Title>
      <Typography.Text type="secondary">仅按状态变更记录串联。缺少历史轨迹 {data.unrecorded_paths} 名。</Typography.Text>
      <Table rowKey="path" size="small" dataSource={data.paths} pagination={{pageSize:5,hideOnSinglePage:true,showSizeChanger:false}}
        columns={[{title:'状态路径',render:(_,row)=>row.path.split(' → ').map(value=>labels[value]||value).join(' → ')},{title:'客户数',dataIndex:'count'}]}/>
      <Typography.Title level={5}>高价值候选特征</Typography.Title>
      <Typography.Text>{data.high_value.threshold===null?'尚未配置匹配度阈值':'匹配度不低于 '+data.high_value.threshold+'，候选 '+data.high_value.count+' 名'}</Typography.Text>
      {data.high_value.threshold!==null&&<div className="report-center-two">
        <CountBars title="候选客户意向国家" counts={data.high_value.countries} labels={{}}/>
        <CountBars title="候选客户学历分布" counts={data.high_value.education} labels={{}}/>
      </div>}
      <Typography.Title level={5}>客户未联系提醒</Typography.Title>
      <Typography.Text>{data.inactive.days===null?'尚未配置提醒天数':'达到 '+data.inactive.days+' 天未联系的客户共 '+data.inactive.count+' 名，按当前授权范围统计。'}</Typography.Text>
      {data.inactive.days!==null&&<Table rowKey="id" size="small" dataSource={data.inactive.items} pagination={{pageSize:5,hideOnSinglePage:true,showSizeChanger:false}}
        columns={[{title:'客户编号',dataIndex:'id'},{title:'未联系天数',dataIndex:'days'}]}/>}
    </Space>}
  </Card>
}

export function ProjectHealth() {
  const {user}=useAuth()
  const result=useQuery({queryKey:[user?.id,'project-health'],
    queryFn:()=>api<{items:{project_id:number;project_name:string;students:number;open_complaints:number;overdue_applications:number;overdue_deadlines:number;score:number|null}[];note:string}>('/api/v1/reporting/board/projects/health')})
  return <Card title="跨项目服务健康度" loading={result.isPending}>
    <ErrorNotice error={result.error}/>
    <Typography.Paragraph type="secondary">{result.data?.note}</Typography.Paragraph>
    <Table rowKey="project_id" size="small" dataSource={result.data?.items||[]} scroll={{x:750}} pagination={{pageSize:5,hideOnSinglePage:true,showSizeChanger:false}}
      columns={[{title:'项目',dataIndex:'project_name'},{title:'在读学生',dataIndex:'students'},
        {title:'有未解决投诉',dataIndex:'open_complaints'},{title:'申请已过期',dataIndex:'overdue_applications'},
        {title:'考务已过期',dataIndex:'overdue_deadlines'},{title:'健康度',render:(_,row)=>row.score===null?'尚未配置权重':row.score+' 分'}]}/>
  </Card>
}
