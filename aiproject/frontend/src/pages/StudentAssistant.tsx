import {useEffect, useRef, useState} from 'react'
import {StudentAssistantGuide, type AssistantTask, type Choice} from './StudentAssistantGuide'
import {Alert, Button, Card, Descriptions, Drawer, Empty, Input, Space, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'

type Request = <T>(path: string, method?: string, body?: unknown, onText?: (text: string) => void) => Promise<T>
type Presentation = {intent?: string; choices?: Choice[]; cards?: FactCard[]}
type Turn = {id: number; role: 'user' | 'assistant'; content: string; presentation?: Presentation}
type Field = {label: string; value: string}
type FactCard = {title: string; fields: Field[]; source_url?: string}
type Task = AssistantTask
type Conversation = {id: string; title: string; update_time?: string}
type Reply = Presentation & {answer: string; conversation_id: string; task?: Task; cards?: FactCard[]; source?: string}
type Overview = {profile: Record<string, string>; applications: {id: number; school: string; major?: string; stage_label: string; next_action?: string; handler?: string; updated_at: string; source: string}[]; notes: string; position: {description: string}; service_stage: {description: string}}
const root = '/api/v1/student/assistant'
const keys = ['visitor', 'student', 'assistant']
const hints = ['想聊聊近况', '我要请假', '查申请进度', '当地生活怎么安排']
const safeUrl = (url?: string) => url && url.toLowerCase().startsWith('https://') ? url : undefined

export function StudentAssistant({request, launch}: {request: Request; launch?: {id: number; query: string}}) {
  const cache = useQueryClient()
  const [activeId, setActiveId] = useState<string>()
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [historyOpen, setHistoryOpen] = useState(false)
  const [factsOpen, setFactsOpen] = useState(false)
  const [replies, setReplies] = useState<Record<string, Reply>>({})
  const [partial, setPartial] = useState('')
  const [showNew, setShowNew] = useState(false)
  const thread = useRef<HTMLDivElement>(null)
  const input = useRef<import('antd/es/input/TextArea').TextAreaRef>(null)
  const selection = useRef(0)
  const consumedLaunch = useRef(0)
  const stick = useRef(true)
  const conversations = useQuery({queryKey: [...keys, 'conversations'], queryFn: () => request<Conversation[]>(root + '/conversations')})
  const detail = useQuery({queryKey: [...keys, 'conversation', activeId], enabled: !!activeId,
    queryFn: () => request<{messages: Turn[]; task?: Task}>(root + '/conversations/' + activeId)})
  const overview = useQuery({queryKey: [...keys, 'overview'], enabled: factsOpen,
    queryFn: () => request<Overview>(root + '/overview'), staleTime: 0})
  async function refresh(cid?: string) {
    await Promise.all([cache.invalidateQueries({queryKey: keys}),
      ...['leaves', 'complaints', 'notifications'].map(key => cache.invalidateQueries({queryKey: ['visitor', 'student', key]}))])
    if (cid) await cache.invalidateQueries({queryKey: [...keys, 'conversation', cid]})
  }
  const send = useMutation({
    mutationFn: (turn: {query: string; cid?: string; selection: number}) => {
      setPartial('')
      return request<Reply>(root, 'POST', {query: turn.query, conversation_id: turn.cid}, setPartial)
    },
    onSuccess: async (reply, turn) => {
      const old = turn.cid || ''
      setDrafts(current => (current[old] || '').trim() === turn.query ? {...current, [old]: ''} : current)
      setReplies(current => ({...current, [reply.conversation_id]: reply}))
      if (!turn.cid && selection.current === turn.selection) {
        setActiveId(reply.conversation_id)
        setDrafts(current => ({...current, [reply.conversation_id]: current[''] || '', '': ''}))
      }
      await refresh(reply.conversation_id)
    },
  })
  const decision = useMutation({
    mutationFn: ({task, cancel}: {task: Task; cancel: boolean}) => request<Task>(root + '/tasks/' + task.id + (cancel ? '/cancel' : '/confirm'), 'POST', {expected_version: task.version}),
    onSuccess: async task => {
      setReplies(current => ({...current, [task.conversation_id]: {...current[task.conversation_id], answer: '', conversation_id: task.conversation_id, task}}))
      await refresh(task.conversation_id)
    },
    onError: () => {void refresh(activeId)},
  })
  const messages = detail.data?.messages || []
  const ownPending = send.isPending && send.variables.cid === activeId
  const ownError = send.error && send.variables?.cid === activeId ? send.error : undefined
  const question = drafts[activeId || ''] || ''
  const latest = activeId ? replies[activeId] : undefined
  // Fresh server detail wins over the immediate response (e.g. after another tab confirms).
  const task = detail.data?.task || latest?.task
  const busy = send.isPending || decision.isPending
  const lastPresentation = messages.filter(turn => turn.role === 'assistant').at(-1)?.presentation || latest
  const guiding = ['leave_create', 'feedback', 'task_result'].includes(lastPresentation?.intent || '')
  useEffect(() => {
    if (thread.current && stick.current) thread.current.scrollTop = messages.length || ownPending || latest ? thread.current.scrollHeight : 0
    else if (messages.length) setShowNew(true)
  }, [activeId, detail.data, ownPending, latest, partial])
  function choose(id?: string) {
    if (!id && busy) return
    selection.current += 1
    setActiveId(id)
    setHistoryOpen(false)
    stick.current = true
    setShowNew(false)
  }
  function sendQuery(query: string) {
    if (!query.trim() || busy) return
    stick.current = true
    send.mutate({query: query.trim(), cid: activeId, selection: selection.current})
  }
  useEffect(() => {
    if (!launch || consumedLaunch.current === launch.id || busy) return
    consumedLaunch.current = launch.id
    selection.current += 1
    setActiveId(undefined)
    send.mutate({query: launch.query, cid: undefined, selection: selection.current})
  }, [launch, busy])
  function submit() {
    if (!question.trim() || busy || detail.isFetching && !!activeId) return
    stick.current = true
    send.mutate({query: question.trim(), cid: activeId, selection: selection.current})
  }
  return <section className="stu-chat" aria-label="学生助手">
    <header className="stu-chat__toolbar">
      <div><Typography.Title level={4} style={{margin: 0}}>学生助手</Typography.Title>
        <Typography.Text type="secondary">留学生活里的问题，或只是想聊聊，我都在这里</Typography.Text></div>
      <Space wrap><Button onClick={() => setHistoryOpen(true)}>对话记录</Button>
        <Button onClick={() => setFactsOpen(true)}>我的当前情况</Button>
        <Button disabled={busy} onClick={() => choose()}>新对话</Button></Space>
    </header>
    <div ref={thread} className="stu-chat__thread" role="log" aria-live="polite" onScroll={e => {
      const el = e.currentTarget
      stick.current = el.scrollHeight - el.clientHeight - el.scrollTop < 64
      if (stick.current) setShowNew(false)
    }}>
      {detail.isFetching && activeId && <Typography.Text type="secondary">正在读取对话…</Typography.Text>}
      {!messages.length && !ownPending && !detail.isFetching && <div className="stu-chat__welcome">
        <span className="student-eyebrow">你好呀，很高兴见到你</span>
        <h2>今天过得怎么样？</h2>
        <p>想聊聊近况、了解当地生活，或是有事情需要安排，都可以从这里开始。</p>
      </div>}
      {messages.map(turn => <article key={turn.id} className={'stu-chat__bubble ' + (turn.role === 'user' ? 'is-user' : '')}>
        <span>{turn.role === 'user' ? '我' : '学生助手'}</span><div>{turn.content}</div>
        {!!turn.presentation?.cards?.length && <div className="stu-chat__cards">{turn.presentation.cards.map((card, index) => <Card size="small" title={card.title} key={index}><Descriptions column={1} items={card.fields.map((field, j) => ({key: j, label: field.label, children: field.value}))}/>{safeUrl(card.source_url) && <a href={safeUrl(card.source_url)} target="_blank" rel="noopener noreferrer">了解官方详情 ↗</a>}</Card>)}</div>}
      </article>)}
      {ownPending && <><article className="stu-chat__bubble is-user"><span>我</span><div>{send.variables.query}</div></article>
        {partial ? <article className="stu-chat__bubble"><span>学生助手</span><div>{partial}</div></article>
          : <p className="stu-chat__working" role="status">正在整理回复…</p>}</>}
      {!ownPending && !!lastPresentation?.choices?.length && <div className="stu-chat__reply-choices">{lastPresentation.choices.map(choice => <Button disabled={busy} key={choice.query} onClick={() => sendQuery(choice.query)}>{choice.label}</Button>)}</div>}
      {!ownPending && task && (guiding || !messages.length) && <StudentAssistantGuide key={task.id + ':' + task.version} task={task} busy={busy} send={sendQuery} decide={cancel => decision.mutate({task, cancel})}/>}
      {!ownPending && task && !guiding && ['collecting', 'awaiting_confirmation'].includes(task.status) && <div className="stu-chat__resume"><span>之前的{task.kind === 'leave' ? '请假' : '反馈'}信息已保留。</span><Button type="link" disabled={busy} onClick={() => sendQuery(task.kind === 'leave' ? '继续请假' : '继续准备反馈')}>继续整理</Button></div>}

    </div>
    {showNew && <Button type="link" onClick={() => {stick.current = true; setShowNew(false); if (thread.current) thread.current.scrollTop = thread.current.scrollHeight}}>查看新消息</Button>}
    {[ownError, detail.error, conversations.error, decision.error].filter(Boolean).map((error, i) => <Alert key={i} type="error" showIcon title={(error as Error).message}/>)}
    <footer className="stu-chat__composer">
      <div className="stu-chat__hints">{hints.map(hint => <button key={hint} type="button" disabled={busy} onClick={() => {setDrafts(current => ({...current, [activeId || '']: hint})); input.current?.focus()}}>{hint}</button>)}</div>
      <div className="stu-chat__input"><Input.TextArea ref={input} aria-label="输入要办的事" value={question} maxLength={1000} autoSize={{minRows: 2, maxRows: 4}} placeholder="说说今天的心情，或你想了解、安排的事情…"
        onChange={e => setDrafts(current => ({...current, [activeId || '']: e.target.value}))}
        onPressEnter={e => {if (!e.nativeEvent.isComposing && e.keyCode !== 229 && !e.shiftKey) {e.preventDefault(); submit()}}}/>
        <Button type="primary" loading={ownPending} disabled={busy || !question.trim()} onClick={submit}>发送</Button></div>
      <Typography.Text type="secondary">Enter 发送 · Shift + Enter 换行。办理事项会先请你核对，再提交。</Typography.Text>
    </footer>
    <Drawer title="对话记录" open={historyOpen} onClose={() => setHistoryOpen(false)} size="default">
      <Button block disabled={busy} onClick={() => choose()}>开始新对话</Button>
      {!conversations.data?.length && <Empty description="还没有对话记录"/>}
      {(conversations.data || []).map(row => <button key={row.id} className={'stu-chat__history ' + (activeId === row.id ? 'is-active' : '')} onClick={() => choose(row.id)}>
        <strong>{row.title}</strong><small>{row.update_time?.slice(0, 16).replace('T', ' ')}</small></button>)}
    </Drawer>
    <Drawer title="我的当前情况" open={factsOpen} onClose={() => setFactsOpen(false)} size="large">
      <Button onClick={() => void overview.refetch()} loading={overview.isFetching}>刷新登记资料</Button>
      {overview.error && <Alert type="error" title={(overview.error as Error).message}/>}
      {overview.data && <><Typography.Paragraph style={{marginTop: 16}}>{overview.data.notes}</Typography.Paragraph>
        <Descriptions column={1} title="学籍登记" items={Object.entries({student_name: '姓名', student_no: '学号', school: '院校', major: '专业', project_name: '所属项目', class_name: '当前班级', class_teacher: '班主任', abroad_country: '留学去向'}).map(([key, label]) => ({key, label, children: overview.data?.profile[key] || '未登记'}))}/>
        <Alert type="info" title={overview.data.service_stage.description} description={overview.data.position.description}/>
        <Typography.Title level={5}>已登记的院校申请</Typography.Title>
        {!overview.data.applications.length && <Empty description="暂无员工登记的申请记录"/>}
        {overview.data.applications.map(row => <Card size="small" key={row.id} title={row.school} style={{marginTop: 12}}>
          <p>{row.major || '专业未登记'} · {row.stage_label}</p><p>下一步：{row.next_action || '请向负责人确认'}</p>
          <p>负责人：{row.handler || '未登记'}</p><small>{row.source} · {row.updated_at.slice(0, 16).replace('T', ' ')}（北京时间）</small>
        </Card>)}</>}
    </Drawer>
  </section>
}
