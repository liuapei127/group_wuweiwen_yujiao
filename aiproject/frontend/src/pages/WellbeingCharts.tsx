import {Card, Empty, Table, Typography} from 'antd'
import {CountBars} from './ReportMetrics'

type Group = {label: string; count: number}
export type WellbeingDistributionData = {
  emotion_tags?: Group[]
  emotion_scores?: Group[]
  alert_reasons?: Group[]
  records_suppressed?: boolean
  milestones?: {label:string;records:number;students:number;average_score:number|null}[]
  items: {status: string; risk_level: string; count: number}[]
}

const riskLabels = {low: '低风险', medium: '中风险', high: '高风险'}
const statusLabels = {pending: '待处理', following: '跟进中', resolved: '已处理', dismissed: '已排除'}
const colors = ['#278675', '#e6ac45', '#cf6863', '#698cc7', '#8c79ad']

function Donut({title, groups, palette = colors}: {title: string; groups: Group[]; palette?: string[]}) {
  const total = groups.reduce((sum, row) => sum + row.count, 0)
  const stops = groups.reduce<{items: string[]; position: number}>((acc, row, index) => {
    const start = acc.position
    const next = start + (total ? row.count / total * 100 : 0)
    return {
      items: [...acc.items, palette[index % palette.length] + ' ' + start + '% ' + next + '%'],
      position: next,
    }
  }, {items: [], position: 0}).items
  return <Card title={title}>
    <Typography.Paragraph type="secondary">按所选周新增预警条数统计</Typography.Paragraph>
    {total ? <div className="wellbeing-donut-layout">
      <div className="wellbeing-donut" role="img"
        aria-label={title + '，' + groups.map(row => row.label + row.count + '条').join('，')}
        style={{background: 'conic-gradient(' + stops.join(',') + ')'}}>
        <div><strong>{total}</strong><span>条预警</span></div>
      </div>
      <ul className="wellbeing-chart-legend">{groups.map((row, index) => <li key={row.label}>
        <span className="wellbeing-chart-dot" style={{background: palette[index % palette.length]}}/>
        <span>{row.label}</span><b>{row.count} 条</b>
        <span>{(row.count / total * 100).toFixed(1)}%</span>
      </li>)}</ul>
    </div> : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="本周暂无预警"/>}
  </Card>
}

export function WellbeingCharts({data}: {data: WellbeingDistributionData}) {
  const risks = Object.entries(riskLabels).map(([key, label]) => ({label,
    count: data.items.filter(row => row.risk_level === key).reduce((sum, row) => sum + row.count, 0)}))
  const states = Object.entries(statusLabels).map(([key, label]) => ({label,
    count: data.items.filter(row => row.status === key).reduce((sum, row) => sum + row.count, 0)}))
  const counts = (groups: Group[] = []) => Object.fromEntries(groups.map(row => [row.label, row.count]))
  const note = data.records_suppressed
    ? '本周已授权心理记录涉及人数低于展示门槛。'
    : '按本周已授权心理记录条数统计，同一学生可有多条记录。仅展示达到人数门槛的分组，占比按可展示记录计算。'
  const scoreOrder = ['0–19', '20–39', '40–59', '60–79', '80–100', '未评分', '无效分值']
  const scores = [...(data.emotion_scores || [])].sort((a, b) => scoreOrder.indexOf(a.label) - scoreOrder.indexOf(b.label))
  return <div className="wellbeing-distributions">
    <Donut title="预警风险等级分布" groups={risks}/>
    <Donut title="预警处理状态分布" groups={states} palette={['#e6ac45', '#698cc7', '#278675', '#89968f']}/>
    <CountBars title="心理记录情绪标签分布" counts={counts(data.emotion_tags)} labels={{}} percentages summary={note}/>
    <CountBars title="心理记录情绪分值分布" counts={counts(scores)} labels={{}} percentages
      summary={<>{note} 分值范围为 0–100，分值越高越积极。</>}/>
    <CountBars title="预警原因分布" counts={counts(data.alert_reasons)} labels={{}} percentages
      summary="按本周新增预警条数统计。根据原因关键词归类，多类命中时依次归入学习压力、生活适应、人际关系、情绪困扰，其余归入其他原因。"/>
    <Card title="留学办理节点与情绪对照">
      <Typography.Paragraph type="secondary">按当周申请、签证与考务截止日期关联心理记录；各组至少涉及五名已授权学生。一个学生可同时有两类截止节点，分组可重叠。</Typography.Paragraph>
      <Table rowKey="label" dataSource={data.milestones||[]} pagination={false} size="small"
        columns={[{title:'当周节点',dataIndex:'label'},{title:'涉及学生',dataIndex:'students'},
          {title:'心理记录',dataIndex:'records'},{title:'平均情绪分值',render:(_,row)=>row.average_score??'未评分'}]}/>
    </Card>
  </div>
}
