import {Button,Card,Typography} from 'antd'
import type {ReactNode} from 'react'

export const statuses: Record<string,string> = {new:'新线索',contacting:'联系中',qualified:'已确认意向',signed:'已签约',lost:'已流失',pending:'待处理',processing:'处理中',resolved:'已处理',closed:'已关闭'}
type Counts = Record<string,number>

export function Metric({label, value, drill}: {label:string; value:ReactNode; drill?:()=>void}) {
  return <Card className="report-center-metric" size="small">
    <Typography.Text type="secondary">{label}</Typography.Text>
    <strong>{value}</strong>
    {drill && <Button type="link" onClick={drill}>查看明细</Button>}
  </Card>
}

export function CountBars({title, counts, labels = statuses, drill, percentages, summary}: {
  title:string; counts:Counts; labels?:Record<string,string>; drill?:(value:string)=>void;
  percentages?:boolean; summary?:ReactNode
}) {
  const entries = Object.entries(counts)
  const max = Math.max(1,...entries.map(([, count])=>count))
  const total = entries.reduce((sum,[,value])=>sum+value,0)
  return <Card title={title} className="report-center-panel">
    {summary && <Typography.Paragraph type="secondary">{summary}</Typography.Paragraph>}
    {entries.length ? entries.map(([name,value])=>{
      const label=labels[name]||name
      const row=<><span>{label}</span><span className="report-center-bar-track" aria-hidden><i style={{width:100*value/max+'%'}}/></span>
        <b>{value}{percentages&&total>0&&<small> · {(value/total*100).toFixed(1)}%</small>}</b></>
      return drill&&value>0
        ? <button type="button" className="report-center-bar report-center-bar-button" key={name}
            aria-label={`${title} · ${label} · ${value} 条明细`} onClick={()=>drill(name)}>{row}</button>
        : <div className="report-center-bar" key={name}>{row}</div>
    }) : <Typography.Text type="secondary">暂无统计数据</Typography.Text>}
  </Card>
}
