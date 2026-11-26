import {Card, Empty, Typography} from 'antd'
import type {ReactNode} from 'react'
import {statuses} from './ReportMetrics'
import {featureLabels} from '../lib/reportLabels'

type Counts = Record<string,number>
const palette = ['#187D71','#4F86A5','#D59A3E','#8B78AF','#C96D66','#78A58B','#9AA7B0']
export type FeatureGroup = {label:string;count:number;signed:number;signed_percent:number}
export type FeatureMetric = 'country'|'education'|'project'|'channel'
export type Department = {department:string|null;new:number;signed:number;lost:number}

export function DistributionChart({title,counts,labels=statuses,variant='horizontal',drill,summary,order}: {
  title:string;counts:Counts;labels?:Record<string,string>;variant?:'horizontal'|'donut'|'columns';
  drill?:(bucket:string)=>void;summary?:ReactNode;order?:string[]
}) {
  const entries = (order ? order.filter(key=>key in counts).map(key=>[key,counts[key]] as const) : Object.entries(counts))
    .filter(([,value])=>Number.isFinite(value)&&value>=0)
  const total=entries.reduce((sum,[,value])=>sum+value,0)
  if(!total)return <Card title={title} role="region" aria-label={title} className="report-center-panel report-distribution" data-chart={variant}>
    {summary&&<Typography.Paragraph type="secondary">{summary}</Typography.Paragraph>}
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前授权范围和所选期间暂无数据"/>
  </Card>
  const max=Math.max(...entries.map(([,value])=>value),1)
  const stops=entries.reduce<{items:string[];offset:number}>((acc,[,value],index)=>{const start=acc.offset;const next=start+value/total*100;return {items:[...acc.items,palette[index%palette.length]+' '+start+'% '+next+'%'],offset:next}},{items:[],offset:0}).items.join(',')
  const label=(key:string)=>labels[key]||key
  const describe=(key:string,value:number)=>title+' · '+label(key)+' · '+value+' 条明细'
  return <Card title={title} role="region" aria-label={title} className="report-center-panel report-distribution" data-chart={variant}>
    {summary&&<Typography.Paragraph type="secondary">{summary}</Typography.Paragraph>}
    {variant==='donut'?<div className="report-donut-layout">
      <div className="report-donut" style={{background:'conic-gradient('+stops+')'}} aria-hidden="true">
        <div><strong>{total}</strong><span>合计</span></div>
      </div>
      <ul className="report-chart-legend">{entries.map(([key,value],index)=><li key={key}>
        <span className="report-chart-dot" style={{background:palette[index%palette.length]}}/>
        {drill&&value>0?<button type="button" aria-label={describe(key,value)} onClick={()=>drill(key)}>{label(key)}</button>:<span>{label(key)}</span>}
        <b>{value}</b><span>{(value/total*100).toFixed(1)}%</span>
      </li>)}</ul>
    </div>:variant==='columns'?<div className="report-columns">
      {entries.map(([key,value],index)=><div className="report-column" key={key}>
        <div className="report-column-plot"><span className="report-column-count">{value}</span>
          <button type="button" aria-label={describe(key,value)} disabled={!drill||!value} onClick={()=>drill?.(key)}
            style={{height:160*value/max,background:palette[index%palette.length]}}/>
        </div><span className="report-column-label">{label(key)}</span><small>{(value/total*100).toFixed(1)}%</small>
      </div>)}
    </div>:entries.map(([key,value],index)=>{
      const row=<><span>{label(key)}</span><span className="report-center-bar-track" aria-hidden="true"><i style={{width:100*value/max+'%',background:palette[index%palette.length]}}/></span>
        <b>{value}<small> · {(value/total*100).toFixed(1)}%</small></b></>
      return drill&&value>0?<button type="button" className="report-center-bar report-center-bar-button" key={key} aria-label={describe(key,value)} onClick={()=>drill(key)}>{row}</button>
        :<div className="report-center-bar" key={key}>{row}</div>
    })}
  </Card>
}

const features = [
  {key:'intended_country',title:'意向国家',metric:'country',variant:'horizontal'},
  {key:'education_level',title:'学历分布',metric:'education',variant:'donut'},
  {key:'intended_project',title:'意向项目',metric:'project',variant:'horizontal'},
  {key:'source_channel',title:'来源渠道分析',metric:'channel',variant:'horizontal'},
] as const
export function CustomerFeatureCharts({groups,onDrill}:{groups:Record<string,FeatureGroup[]>;onDrill:(metric:FeatureMetric,bucket:string)=>void}) {
  return <div className="report-center-two">{features.map(feature=>{
    const rows=groups[feature.key]||[]
    return <DistributionChart key={feature.key} title={feature.title} variant={feature.variant} labels={featureLabels[feature.key]||{}}
      counts={Object.fromEntries(rows.map(row=>[row.label,row.count]))} drill={bucket=>onDrill(feature.metric,bucket)}
      summary="按所选期间新增客户统计。"/>
  })}</div>
}

export function DepartmentChart({rows,onDrill}:{rows:Department[];onDrill:(department:string|null,metric:'new'|'signed'|'lost')=>void}) {
  if(!rows.length)return <Card title="部门经营对比" role="region" aria-label="部门经营对比">
    <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="当前授权范围和所选期间暂无部门经营数据"/>
  </Card>
  const series=[{key:'new',label:'新增线索'},{key:'signed',label:'签约记录'},{key:'lost',label:'流失记录'}] as const
  const max=Math.max(1,...rows.flatMap(row=>series.map(item=>row[item.key])))
  return <Card title="部门经营对比" role="region" aria-label="部门经营对比" data-chart="grouped" className="report-center-panel">
    <div className="report-series-legend">{series.map((item,index)=><span key={item.key}><i style={{background:palette[index]}}/>{item.label}</span>)}</div>
    <Typography.Paragraph type="secondary">新增线索按创建日期统计；签约与流失按状态变更日期统计。</Typography.Paragraph>
    <div className="report-departments">{rows.map(row=><div className="report-department" key={row.department??'missing'}>
      <strong>{row.department||'未填写部门'}</strong><div>{series.map((item,index)=><button type="button" key={item.key} disabled={!row[item.key]}
        aria-label={(row.department||'未填写部门')+' · '+item.label+' · '+row[item.key]+' 条明细'} onClick={()=>onDrill(row.department,item.key)}>
        <span>{item.label}</span><span className="report-center-bar-track" aria-hidden="true"><i style={{width:100*row[item.key]/max+'%',background:palette[index]}}/></span><b>{row[item.key]}</b>
      </button>)}</div>
    </div>)}</div>
  </Card>
}
