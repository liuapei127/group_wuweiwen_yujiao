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

export function CountBars({title, counts}: {title:string; counts:Counts}) {
  const entries = Object.entries(counts)
  const max = Math.max(1,...entries.map(([, count])=>count))
  return <Card title={title} className="report-center-panel">
    {entries.length ? entries.map(([name,value])=><div className="report-center-bar" key={name}>
      <span>{statuses[name] || name}</span><div><i style={{width:100*value/max+'%'}}/></div><b>{value}</b>
    </div>) : <Typography.Text type="secondary">暂无统计数据</Typography.Text>}
  </Card>
}
