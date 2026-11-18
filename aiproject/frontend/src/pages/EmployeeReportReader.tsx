import {Empty, Skeleton, Typography} from 'antd'
import dayjs from 'dayjs'
import {ErrorNotice} from '../components/shared'

type Report = {
  content: string
  key_progress?: unknown
  risks?: unknown
  next_plan?: string | null
}
type WeeklyReport = Report & {week_start: string; submitted_at?: string}

export type StaffDetail = {
  real_name: string
  weekly_report?: WeeklyReport | null
  reports: (Report & {id: number; report_date: string})[]
}

function readableNotes(value: unknown): string[] {
  if (typeof value === 'string') return value.trim() ? [value] : []
  if (Array.isArray(value)) return value.flatMap(readableNotes)
  if (value && typeof value === 'object') {
    const record = value as Record<string, unknown>
    return readableNotes(record.items ?? record.text ?? record.content ?? record.description)
  }
  return []
}

export function EmployeeReportReader({period, detail, loading, error}: {
  period: 'day' | 'week'
  detail?: StaffDetail; loading: boolean; error: unknown
}) {
  const weekly = period === 'week'
  const records = weekly
    ? detail?.weekly_report ? [{...detail.weekly_report, date: detail.weekly_report.week_start}] : []
    : (detail?.reports || []).map(row => ({...row, date: row.report_date}))
  if (loading) return <Skeleton active paragraph={{rows: 8}}/>
  if (error) return <ErrorNotice error={error}/>
  if (!detail) return null
  if (!records.length) return <Empty description={weekly ? '本周尚未提交周报' : '当日尚未提交日报'}/>
  return <div className="employee-report-reader">
    <section aria-label={weekly ? '周报原文' : '日报原文'}>
      <Typography.Title level={4}>{weekly ? '周报原文' : '日报原文'}</Typography.Title>
      {records.map(row => <article key={row.date} className="employee-report-original">
        <Typography.Text type="secondary">
          {weekly ? `周报周期：${row.date} 至 ${dayjs(row.date).add(6, 'day').format('YYYY-MM-DD')}` : row.date}
        </Typography.Text>
        <Typography.Paragraph className="employee-report-text">{row.content}</Typography.Paragraph>
        {([
          ['关键进展', readableNotes(row.key_progress)],
          ['风险事项', readableNotes(row.risks)],
          ['下一步计划', readableNotes(row.next_plan)],
        ] as const).map(([label, notes]) => notes.length > 0 && <div key={label}>
          <Typography.Text strong>{label}</Typography.Text>
          {notes.map((note, index) => <Typography.Paragraph key={index} className="employee-report-text">{note}</Typography.Paragraph>)}
        </div>)}
      </article>)}
    </section>
  </div>
}
