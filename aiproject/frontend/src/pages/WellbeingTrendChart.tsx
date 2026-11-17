import {useState} from 'react'
import './wellbeing-trend.css'

export type WellbeingWeek = {
  period_start:string;period_end:string;eligible:number;participants:number|null;suppressed:boolean;
  items:{risk_level:string;count:number}[]
}

export function WellbeingTrendChart({weeks}:{weeks:WellbeingWeek[]}) {
  const [selected,setSelected]=useState<string>()
  const rows=[...weeks].sort((a,b)=>a.period_start.localeCompare(b.period_start)).map(week=>({...week,
    total:week.items.reduce((sum,item)=>sum+item.count,0),
    high:week.items.filter(item=>item.risk_level==='high').reduce((sum,item)=>sum+item.count,0),
  }))
  if(!rows.length)return null
  const active=rows.find(row=>row.period_start===selected)??rows[rows.length-1]
  const step=Math.max(1,Math.ceil(Math.max(...rows.map(row=>row.total))/4))
  const ceiling=step*4
  const left=48,right=760,top=28,bottom=242
  const x=(index:number)=>rows.length===1?(left+right)/2:left+index*(right-left)/(rows.length-1)
  const y=(value:number)=>bottom-value/ceiling*(bottom-top)
  const series=[{key:'total',label:'新增预警',color:'#187D71'},{key:'high',label:'高风险预警',color:'#C65D58'}] as const
  const describe=(row:typeof rows[number])=>row.period_start+' 至 '+row.period_end+'，新增预警 '+row.total+' 条，高风险预警 '+row.high+' 条'
  return <figure className="wellbeing-trend-chart" aria-label="每周预警数量趋势">
    <figcaption><strong>每周预警数量</strong><div className="wellbeing-trend-legend">{series.map(item=><span key={item.key}>
      <i style={{borderColor:item.color,borderTopStyle:item.key==='high'?'dashed':'solid'}}/>{item.label}
    </span>)}</div></figcaption>
    <p className="wellbeing-trend-note">高风险预警包含在新增预警中，按条数统计。当周数据会随新增记录更新。</p>
    <div className="wellbeing-trend-scroll">
      <svg viewBox="0 0 808 294" role="img" aria-label="新增预警与高风险预警按周对比折线图，横轴为周起始日期，纵轴为预警条数">
        <text x={left} y={14} className="wellbeing-trend-label">条</text>
        {Array.from({length:5},(_,index)=>index*step).map(tick=><g key={tick}>
          <line x1={left} x2={right} y1={y(tick)} y2={y(tick)} stroke="#E4EAE7" strokeDasharray={tick?'4 4':undefined}/>
          <text x={left-12} y={y(tick)+4} textAnchor="end" className="wellbeing-trend-label">{tick}</text>
        </g>)}
        {series.map(item=><polyline key={item.key} data-series={item.key} fill="none" stroke={item.color} strokeWidth={3}
          strokeDasharray={item.key==='high'?'7 5':undefined} strokeLinejoin="round" strokeLinecap="round"
          points={rows.map((row,index)=>x(index)+','+y(row[item.key])).join(' ')}/>)}
        {rows.map((row,index)=><g key={row.period_start} tabIndex={0} role="group" aria-label={describe(row)}
          className="wellbeing-trend-point" onFocus={()=>setSelected(row.period_start)} onMouseEnter={()=>setSelected(row.period_start)}
          onClick={()=>setSelected(row.period_start)}>
          <title>{describe(row)}</title>
          <rect x={x(index)-24} y={top-8} width={48} height={bottom-top+16} fill="transparent"/>
          <line className="wellbeing-trend-guide" x1={x(index)} x2={x(index)} y1={top} y2={bottom} stroke="#A6B8B1" strokeDasharray="3 3"/>
          {series.map(item=><g key={item.key}>
            <circle cx={x(index)} cy={y(row[item.key])} r={item.key==='total'?5:3} fill="white" stroke={item.color} strokeWidth={2}/>
            <text x={x(index)} y={y(row[item.key])+(item.key==='total'?-12:20)} textAnchor="middle" fill={item.color} fontSize={12}>{row[item.key]}</text>
          </g>)}
          <text x={x(index)} y={bottom+39} textAnchor="middle" className="wellbeing-trend-label">{row.period_start.slice(5).replace('-','/')}</text>
        </g>)}
        <text x={right} y={290} textAnchor="end" className="wellbeing-trend-label">周起始日期</text>
      </svg>
    </div>
    <div className="wellbeing-trend-detail" aria-live="polite">
      <strong>{active.period_start} 至 {active.period_end}</strong>
      <span>新增预警 <b>{active.total}</b> 条</span><span>高风险预警 <b>{active.high}</b> 条</span>
      <span>{active.suppressed?'自评参与人数低于展示门槛':active.participants===null?'自评参与人数暂无数据':'参与自评 '+active.participants+' 人'}</span>
    </div>
  </figure>
}
