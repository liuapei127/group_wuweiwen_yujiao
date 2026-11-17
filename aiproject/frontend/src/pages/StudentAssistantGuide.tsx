import {useState} from 'react'
import {Alert, Button, Card, Descriptions, Input, Space, Tag} from 'antd'
export type Choice = {label: string; query: string; description?: string}
export type AssistantTask = {id: string; conversation_id: string; status: string; version: number; kind: string; fields: {label: string; value: string}[]; missing: string[]; result?: {id: number}; form_values?: Record<string, string>; guide?: {kind: string; question: string; hint?: string; field?: string; placeholder?: string; suggested_text?: string; step: number; total: number; choices?: Choice[]}}
export function StudentAssistantGuide({task, busy, send, decide}: {task: AssistantTask; busy: boolean; send: (text: string) => void; decide: (cancel: boolean) => void}) {
  const [start, setStart] = useState(task.form_values?.start_time || '')
  const [end, setEnd] = useState(task.form_values?.end_time || '')
  const [text, setText] = useState(task.guide?.suggested_text || '')
  const [error, setError] = useState('')
  const guide = task.guide
  if (task.status === 'submitted') return <Alert className="stu-chat__task" type="success" showIcon title={'已提交，记录 #' + task.result?.id} description="接下来等待负责人员处理。你可以到对应栏目查看进度。"/>
  if (task.status === 'cancelled') return <p className="stu-chat__task-end">这次没有提交，需要时我们再继续。</p>
  if (task.status === 'expired') return <Alert type="info" title="这份信息已过期，请重新确认时间和内容。"/>
  if (!guide) return null
  function submitDates() {
    if (!start || !end || !Number.isFinite(Date.parse(start)) || !Number.isFinite(Date.parse(end)) || Date.parse(start) >= Date.parse(end)) {setError('请选择有效的开始和结束时间，结束应晚于开始。'); return}
    setError(''); send('请假起止时间：' + start.replace('T', ' ') + ' 到 ' + end.replace('T', ' '))
  }
  return <section className="stu-guide" aria-label={task.kind === 'leave' ? '请假引导' : '反馈引导'}>
    <div className="stu-guide__heading"><span>{task.kind === 'leave' ? '一起准备请假' : '一起整理反馈'}</span><small>第 {guide.step} / {guide.total} 步</small></div>
    {guide.kind === 'choice' && <div className="stu-guide__choices">{guide.choices?.map(choice => <button disabled={busy} key={choice.query} onClick={() => send(choice.query)}><strong>{choice.label}</strong><span>{choice.description}</span></button>)}</div>}
    {guide.kind === 'datetime' && <div className="stu-guide__dates"><p>{guide.hint}</p><label>开始时间<Input aria-label="请假开始时间" type="datetime-local" value={start} disabled={busy} onChange={event => setStart(event.target.value)}/></label><label>结束时间<Input aria-label="请假结束时间" type="datetime-local" value={end} disabled={busy} onChange={event => setEnd(event.target.value)}/></label><Button type="primary" disabled={busy} onClick={submitDates}>下一步</Button></div>}
    {guide.kind === 'text' && <div className="stu-guide__text"><Input.TextArea aria-label={guide.field === 'reason' ? '请假原因' : '反馈具体情况'} value={text} disabled={busy} maxLength={2000} autoSize={{minRows: 2, maxRows: 4}} placeholder={guide.placeholder} onChange={event => setText(event.target.value)}/><Button type="primary" disabled={busy || !text.trim()} onClick={() => send((guide.field === 'reason' ? '事由：' : '内容：') + text.trim())}>核对信息</Button></div>}
    {guide.kind === 'review' && <Card size="small" title={task.kind === 'leave' ? '请假信息确认' : '反馈信息确认'} extra={<Tag color="gold">尚未提交</Tag>}><Descriptions column={1} items={task.fields.map((field, i) => ({key: i, label: field.label, children: field.label.includes('时间') ? field.value.replace('T', ' ') : field.value}))}/><Space><Button type="primary" disabled={busy} onClick={() => decide(false)}>确认提交</Button><Button disabled={busy} onClick={() => {send(task.kind === 'leave' ? '我要修改请假时间' : '我要修改反馈内容')}}>修改信息</Button></Space></Card>}
    {error && <Alert type="warning" title={error}/>}
    <Button className="stu-guide__cancel" type="text" disabled={busy} onClick={() => decide(true)}>这次先不提交</Button>
  </section>
}
