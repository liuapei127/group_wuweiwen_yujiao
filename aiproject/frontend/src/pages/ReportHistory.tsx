import {useState} from 'react'
import {App, Button, Collapse, Drawer, Input, Select, Space, Table, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ErrorNotice} from '../components/shared'
import {api, download, query} from '../lib/api'

export type ReportKind = 'customer_ops' | 'complaint_weekly' | 'daily_summary' | 'weekly_summary' | 'psych_weekly'

type ArchiveEntry = {
  id: number; report_title?: string; period_start?: string; period_end?: string
  report_content?: Record<string, unknown>; unavailable?: boolean; format?: 'formal'; create_time?: string
}
const endpoint = '/api/v1/reporting'
const statusLabels: Record<string, string> = {new: '新线索', contacting: '联系中', qualified: '已确认意向',
  signed: '已签约', lost: '已流失', pending: '待处理', processing: '处理中', resolved: '已处理',
  closed: '已关闭', following: '跟进中', dismissed: '已排除'}
const riskLabels: Record<string, string> = {low: '低', medium: '中', high: '高'}

function summarize(report: ArchiveEntry) {
  const content = report.report_content || {}
  const counts = (values: Record<string, unknown>) => Object.entries(values).map(([state, count]) => ({
    状态: statusLabels[state] || state, 数量: count,
  }))
  const sections = content.sections as Record<string, string> | undefined
  const submissions=content.submissions as {expected:number;submitted:number;missing:number;departments:{department:string|null;expected:number;submitted:number;missing:number}[]} | undefined
  if (content.days) return {
    ...(submissions && {应交:submissions.expected,已交:submissions.submitted,未交:submissions.missing,
      分部门提交:submissions.departments.map(r=>({部门:r.department||'未填写部门',应交:r.expected,已交:r.submitted,未交:r.missing}))}),
    ...(sections && {
      工作总结: sections.work_summary,
      关键进展: sections.key_progress_summary,
      风险事项: sections.risk_summary,
      下一步建议: sections.next_work_suggestions,
    }),
    累计提交人次: content.submitted_employee_days,
    每日人数: (content.days as {report_date: string; submitted_employees: number}[]).map(row =>
      ({日期: row.report_date, 提交人数: row.submitted_employees})),
  }
  const extras = {
    ...(content.ai_summary ? {AI摘要:content.ai_summary} : {}),
    ...(content.suggestion ? {审核建议:content.suggestion} : {}),
  }
  if (content.items) return {...extras, ...(content.eligible!==undefined ? {统计范围:content.eligible,
    参与自评:content.suppressed?'低于展示人数':content.participants,
    情绪趋势:(content.emotion as {day:string;label:string;count:number}[]).map(r=>({日期:r.day,分类:r.label,人数:r.count})),
    压力趋势:(content.stress as {day:string;label:string;count:number}[]).map(r=>({日期:r.day,分类:r.label,人数:r.count})),
  } : {}), 心理预警: (content.items as {status: string; risk_level: string; count: number}[]).map(row =>
    ({状态: statusLabels[row.status], 风险: riskLabels[row.risk_level], 数量: row.count}))}
  if (content.complaints_by_status) return {...extras, 投诉状态: counts(content.complaints_by_status as Record<string, unknown>),
    ...(content.categories ? {投诉分类:counts(content.categories as Record<string,unknown>),
      积压账龄:counts(content.backlog as Record<string,unknown>),满意度:counts(content.satisfaction as Record<string,unknown>)} : {}),
    ...(content.as_of ? {积压快照时间:content.as_of} : {}),
  }
  return {线索状态: counts((content.leads_by_status || {}) as Record<string, unknown>),
    ...(content.transitions ? {已记录的状态变更:counts(content.transitions as Record<string,unknown>),
      流失原因:counts(content.lost_reasons as Record<string,unknown>),实际开始记录日:content.status_history_since} : {}),
  }
}

const PAGE_SIZE = 5

export function ReportHistory({kind}: {kind?: ReportKind}) {
  const [expanded, setExpanded] = useState(false)
  return <Collapse className="report-history" onChange={keys => setExpanded(keys.includes('history'))} items={[{
    key: 'history',
    label: '历史报告',
    children: <ReportHistoryList key={kind} kind={kind} expanded={expanded}/>,
  }]}/>
}

function ReportHistoryList({kind, expanded}: {kind?: ReportKind; expanded: boolean}) {
  const {user, can} = useAuth()
  const {message} = App.useApp()
  const cache = useQueryClient()
  const [history, setHistory] = useState<(number | undefined)[]>([undefined])
  const [detailId, setDetailId] = useState<number>()
  const [shared, setShared] = useState(false)
  const [suggestion, setSuggestion] = useState('')
  const records = useQuery({
    queryKey: [user?.id, 'report-archive', kind, shared, history.at(-1)],
    queryFn: () => api<ArchiveEntry[]>(endpoint + '/archive' +
      query({kind, shared, before_id: history.at(-1), limit: PAGE_SIZE + 1})),
    enabled: expanded,
    refetchInterval: expanded && history.length === 1 ? 30_000 : false,
  })
  const rows = records.error ? [] : records.data?.slice(0, PAGE_SIZE) || []
  const detail = rows.find(row => row.id === detailId && !row.unavailable)
  const hasNext = !records.error && (records.data?.length ?? 0) > PAGE_SIZE
  const review = useMutation({
    mutationFn: ({id, suggestion}: {id: number; suggestion: string}) =>
      api(endpoint + '/wellbeing/reports/' + id + '/review', {method: 'POST', body: {suggestion}}),
    onSuccess: async () => {
      await cache.invalidateQueries({queryKey: [user?.id, 'report-archive']})
      void message.success('心理周报已发布')
    },
  })
  return <>
    <Select aria-label="归档查看范围" value={shared} style={{minWidth:190,marginBottom:16}}
      options={[{value:false,label:'本人生成的归档'},{value:true,label:'授权范围共享归档'}]}
      onChange={value=>{setShared(value);setHistory([undefined]);setDetailId(undefined)}}/>
    <ErrorNotice error={records.error}/>
      <Table rowKey="id" size="small" pagination={false} loading={records.isFetching} dataSource={rows}
      locale={{emptyText: '暂无历史报告'}} scroll={{x: 760}} columns={[
        {title: '报告', render: (_, row) => row.unavailable ? '权限已变更' : row.report_title},
        {title: '类型', render: (_, row) => row.unavailable ? '—' : row.format === 'formal' ? '正式 AI 报告' : row.report_content?.review_status === 'draft' ? '待审核' : row.report_content?.review_status === 'published' ? '已发布' : '统计快照'},
        {title: '生成时间（北京时间）', render: (_, row) => row.create_time?.replace('T', ' ') || '—'},
        {title: '统计期间', render: (_, row) => row.period_start ? row.period_start + ' 至 ' + row.period_end : '—'},
        {title: '操作', render: (_, row) => !row.unavailable && <Space wrap>
          <Button type="link" onClick={() => {setSuggestion(String(row.report_content?.ai_summary??''));review.reset();setDetailId(row.id)}}>查看报告</Button>
          <Button type="link" onClick={() => void download(endpoint + '/archive/' + row.id + '/pdf' + query({shared}),
            (row.report_title || '报表') + '-' + row.id + '.pdf').catch((error: Error) => void message.error(error.message))}>下载 PDF</Button>
        </Space>},
      ]}/>
    <Space style={{marginTop: 12}} wrap>
      <Button disabled={history.length === 1 || records.isFetching}
        onClick={() => {setDetailId(undefined); setHistory(cursors => cursors.slice(0, -1))}}>上一页</Button>
      <Typography.Text type="secondary">第 {history.length} 页</Typography.Text>
      <Button disabled={!hasNext || records.isFetching}
        onClick={() => {
          const lastId = rows.at(-1)?.id
          if (lastId === undefined) return
          setDetailId(undefined)
          setHistory(cursors => [...cursors, lastId])
        }}>下一页</Button>
      <Button loading={records.isFetching} onClick={() => void records.refetch()}>刷新</Button>
    </Space>
    <Drawer title={detail?.report_title || '报告'} open={!!detail} onClose={() => setDetailId(undefined)} size="large">
      {detail && <>
        <Typography.Paragraph type="secondary">{detail.period_start} 至 {detail.period_end}</Typography.Paragraph>
        {detail.report_content?.review_status==='draft' && can('student-alerts:write') && !can('reports:wellbeing:read') &&
          <Space orientation="vertical" style={{width:'100%',marginBottom:16}}>
            <ErrorNotice error={review.error}/>
            <Input.TextArea aria-label="审核建议" value={suggestion} maxLength={4000} rows={4}
              onChange={e=>setSuggestion(e.target.value)}/>
            <Button type="primary" loading={review.isPending} disabled={!suggestion.trim()}
              onClick={()=>review.mutate({id:detail.id,suggestion:suggestion.trim()})}>审核并发布</Button>
          </Space>}
        {Object.entries(summarize(detail)).map(([label, value]) => <section key={label}>
          <Typography.Title level={5}>{label}</Typography.Title>
          {Array.isArray(value) ? <Table
            size="small" pagination={false} dataSource={value.map((row, id) => ({...row, id}))} rowKey="id"
            columns={Object.keys(value[0] || {}).map(key => ({title: key, dataIndex: key}))}
            locale={{emptyText: '本期无相关记录'}}
          /> : <Typography.Paragraph style={{whiteSpace: 'pre-wrap'}}>{String(value ?? '—')}</Typography.Paragraph>}
        </section>)}
      </>}
    </Drawer>
  </>
}
