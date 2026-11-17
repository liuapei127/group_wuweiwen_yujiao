import {Card, Table, Typography} from 'antd'
import {useQuery} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ErrorNotice} from '../components/shared'
import {api, query} from '../lib/api'
import type {FeatureGroup} from './ReportCharts'
import {WellbeingTrendChart,type WellbeingWeek} from './WellbeingTrendChart'

type Comparison = {start:string;end:string;count:number;change:number;percent:number|null}
type Timing = {samples:number;average_hours:number|null}
export type AnalysisResult = {comparisons?:Record<string,Comparison>;groups?:Record<string,FeatureGroup[]>;
  first_response?:Timing;resolution?:Timing;note?:string;overdue_days?:number|null;resolution_overdue_percent?:number|null;late_resolutions?:number|null}
export function useOperationAnalysis(kind:'customers'|'complaints',start:string,end:string,enabled=true) {
  const {user}=useAuth()
  return useQuery({queryKey:[user?.id,'report-analysis',kind,start,end],
    queryFn:()=>api<AnalysisResult>('/api/v1/reporting/board/'+kind+'/analysis'+query({start,end})),enabled:enabled&&!!start&&!!end})
}
export function OperationAnalysis({kind,start,end}:{kind:'customers'|'complaints';start:string;end:string}) {
  const result=useOperationAnalysis(kind,start,end)
  const data=result.data
  const timings=([['首次响应',data?.first_response],['首次解决',data?.resolution]] as const)
    .filter(([,value])=>value&&value.samples>0&&value.average_hours!==null)
  if(result.error)return <ErrorNotice error={result.error}/>
  if(!timings.length)return null
  return <Card title="投诉处理时效">
    <div className="report-center-two">{timings.map(([label,value])=><div key={label}>
      <Typography.Text strong>{label}平均耗时</Typography.Text>
      <Typography.Title level={3}>{value!.average_hours} 小时</Typography.Title>
      <Typography.Text type="secondary">有效样本 {value!.samples} 条</Typography.Text>
    </div>)}</div>
    {data?.note&&<Typography.Paragraph type="secondary">{data.note}</Typography.Paragraph>}
    {data?.overdue_days!=null&&data.resolution_overdue_percent!=null&&<Typography.Paragraph type="secondary">
      超时标准 {data.overdue_days} 天；已记录解决样本中超时 {data.late_resolutions??0} 条，超时率 {data.resolution_overdue_percent}%
    </Typography.Paragraph>}
  </Card>
}

type Week = WellbeingWeek
export function WellbeingTrend({anchor}:{anchor:string}) {
  const {user}=useAuth()
  const result=useQuery({queryKey:[user?.id,'wellbeing-trend',anchor],enabled:!!anchor,
    queryFn:()=>api<{weeks:Week[]}>('/api/v1/reporting/wellbeing/trend'+query({anchor}))})
  return <Card title="近八周心理健康趋势" loading={result.isPending}>
    <ErrorNotice error={result.error}/>
    <Typography.Paragraph type="secondary">各周均按当前可查看的学生范围统计。自评参与人数沿用现有展示门槛。</Typography.Paragraph>
    {!result.error&&<WellbeingTrendChart weeks={result.data?.weeks||[]}/>}
    <Table<Week> rowKey="period_start" dataSource={result.data?.weeks||[]} pagination={false} size="small" scroll={{x:650}}
      columns={[{title:'周报期间',render:(_,row)=>row.period_start+' 至 '+row.period_end},
        {title:'参与自评',render:(_,row)=>row.suppressed?'低于展示人数':row.participants},
        {title:'覆盖率',render:(_,row)=>row.suppressed||!row.eligible?'—':Math.round((row.participants||0)/row.eligible*100)+'%'},
        {title:'新增预警',render:(_,row)=>row.items.reduce((sum,item)=>sum+item.count,0)},
        {title:'高风险预警',render:(_,row)=>row.items.filter(item=>item.risk_level==='high').reduce((sum,item)=>sum+item.count,0)}]}/>
  </Card>
}

export function ProjectHealth() {
  const {user}=useAuth()
  const result=useQuery({queryKey:[user?.id,'project-health'],
    queryFn:()=>api<{items:{project_id:number;project_name:string;students:number;open_complaints:number;overdue_applications:number;overdue_deadlines:number;score:number|null}[];note:string}>('/api/v1/reporting/board/projects/health')})
  if(!result.isPending&&!result.error&&!result.data?.items.length)return null
  return <Card title="跨项目服务健康度" loading={result.isPending}>
    <ErrorNotice error={result.error}/>
    <Typography.Paragraph type="secondary">{result.data?.note}</Typography.Paragraph>
    <Table rowKey="project_id" size="small" dataSource={result.data?.items||[]} scroll={{x:750}} pagination={{pageSize:5,hideOnSinglePage:true,showSizeChanger:false}}
      columns={[{title:'项目',dataIndex:'project_name'},{title:'在读学生',dataIndex:'students'},
        {title:'有未解决投诉',dataIndex:'open_complaints'},{title:'申请已过期',dataIndex:'overdue_applications'},
        {title:'考务已过期',dataIndex:'overdue_deadlines'},{title:'健康度',render:(_,row)=>row.score===null?'—':row.score+' 分'}]}/>
  </Card>
}
