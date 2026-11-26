import {Fragment, useEffect, useLayoutEffect, useRef, useState} from 'react'
import {StudentAssistantGuide, type AssistantTask, type Choice} from './StudentAssistantGuide'
import {StudentMemory} from './StudentMemory'
import {assistantTurnStored, newestAssistantTask, orderAssistantTurns, assistantCardLayout, replyScrollTarget, replyReadingAction, additionalOfficialSources} from './student-assistant-state'
import {Alert, Button, Card, Descriptions, Drawer, Empty, Input, Space, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'

type Request = <T>(path: string, method?: string, body?: unknown, onText?: (text: string) => void) => Promise<T>
type Presentation = {reply_notice?: string; intent?: string; choices?: Choice[]; cards?: FactCard[]; facts_kind?: 'public_knowledge' | 'student_record'; knowledge_keys?: string[]}
type Turn = {id: number; role: 'user' | 'assistant'; content: string; presentation?: Presentation}
type Field = {label: string; value: string}
type FactCard = {title: string; fields: Field[]; source_url?: string; sources?: {title: string; url: string}[]}
type Task = AssistantTask
type Conversation = {id: string; title: string; update_time?: string}
type Reply = Presentation & {answer: string; conversation_id: string; task?: Task; cards?: FactCard[]; source?: string; receivedAt?: number; history_warning?: string; clientQuery?: string; afterMessageId?: number; localRequestId?: number}
type Overview = {profile: Record<string, string>; applications: {id: number; school: string; major?: string; stage_label: string; next_action?: string; handler?: string; updated_at: string; source: string}[]; notes: string; position: {description: string}; service_stage: {description: string}}
type SendTurn = {query: string; cid?: string; selection: number; id: number; fromInput: boolean; afterMessageId: number}
type LocalTurn = {id: number; query: string; reply: Reply; afterMessageId: number; warning: string}
type FailedTurn = {query: string; message: string}
const root = '/api/v1/student/assistant'
const keys = ['visitor', 'student', 'assistant']
const hints = ['想聊聊近况', '我要请假', '查申请进度', '当地生活怎么安排']
const safeUrl = (url?: string) => url && url.toLowerCase().startsWith('https://') ? url : undefined

function Cards({cards, presentation, onToggle}: {cards?: FactCard[]; presentation?: Presentation; onToggle?: () => void}) {
  return cards?.length ? <div className={'stu-chat__cards' + (cards.every(card => assistantCardLayout(presentation, card) === 'source') ? ' is-sources' : '')}>{cards.map((card, index) => assistantCardLayout(presentation, card) === 'source' ?
    <div className="stu-chat__source" key={index}>
      {safeUrl(card.source_url) ? <a href={safeUrl(card.source_url)} target="_blank" rel="noopener noreferrer">来源：{card.title} ↗</a> : <span>来源：{card.title}</span>}
      {(!!card.fields.length || !!additionalOfficialSources(card).length) && <details onToggle={onToggle}><summary>来源信息</summary><dl>{card.fields.map((field, j) => <div key={j}><dt>{field.label}</dt><dd>{field.value}</dd></div>)}{additionalOfficialSources(card).map(source => <div key={source.url}><dt>官方资料</dt><dd><a href={source.url} target="_blank" rel="noopener noreferrer">{source.title} ↗</a></dd></div>)}</dl></details>}
    </div> : <Card size="small" title={card.title} key={index}>
      <Descriptions column={1} items={card.fields.map((field, j) => ({key: j, label: field.label, children: field.value}))}/>
      {safeUrl(card.source_url) && <a href={safeUrl(card.source_url)} target="_blank" rel="noopener noreferrer">了解官方详情 ↗</a>}
    </Card>)}</div> : null
}

export function StudentAssistant({request, launch}: {request: Request; launch?: {id: number; query: string}}) {
  const cache = useQueryClient()
  const [activeId, setActiveId] = useState<string>()
  const [drafts, setDrafts] = useState<Record<string, string>>({})
  const [failed, setFailed] = useState<Record<string, FailedTurn | undefined>>({})
  const [historyOpen, setHistoryOpen] = useState(false)
  const [factsOpen, setFactsOpen] = useState(false)
  const [memoriesOpen, setMemoriesOpen] = useState(false)
  const [hintsOpen, setHintsOpen] = useState(false)
  const [replies, setReplies] = useState<Record<string, Reply>>({})
  const [partial, setPartial] = useState<{id: number; text: string}>()
  const [syncWarning, setSyncWarning] = useState('')
  const [localTurns, setLocalTurns] = useState<Record<string, LocalTurn[]>>({})
  const [readingAction, setReadingAction] = useState<'latest' | 'continue'>()
  const thread = useRef<HTMLDivElement>(null)
  const input = useRef<import('antd/es/input/TextArea').TextAreaRef>(null)
  const selection = useRef(0)
  const consumedLaunch = useRef(0)
  const requestCount = useRef(0)
  const inFlight = useRef(false)
  const followReply = useRef(true)
  const programmedScroll = useRef<number | undefined>(undefined)
  const conversations = useQuery({queryKey: [...keys, 'conversations'], queryFn: () => request<Conversation[]>(root + '/conversations')})
  const detail = useQuery({queryKey: [...keys, 'conversation', activeId], enabled: !!activeId,
    queryFn: () => request<{messages: Turn[]; task?: Task}>(root + '/conversations/' + activeId)})
  const overview = useQuery({queryKey: [...keys, 'overview'], enabled: factsOpen,
    queryFn: () => request<Overview>(root + '/overview'), staleTime: 0})
  async function refresh(cid?: string) {
    await Promise.all([cache.invalidateQueries({queryKey: keys}, {throwOnError: true}),
      ...['leaves', 'complaints', 'notifications', 'home', 'home-notices'].map(key => cache.invalidateQueries({queryKey: ['visitor', 'student', key]}))])
    if (cid) await cache.invalidateQueries({queryKey: [...keys, 'conversation', cid]}, {throwOnError: true})
  }
  const send = useMutation({
    mutationFn: (turn: SendTurn) => request<Reply>(root, 'POST', {query: turn.query, conversation_id: turn.cid},
      text => setPartial({id: turn.id, text})),
    onSuccess: async (reply, turn) => {
      setReplies(current => ({...current, [reply.conversation_id]: {...reply, receivedAt: Date.now(), localRequestId: turn.id, clientQuery: turn.query, afterMessageId: turn.afterMessageId}}))
      setFailed(current => ({...current, [turn.cid || '']: undefined}))
      let warning = reply.history_warning || ''
      try {
        await refresh(reply.conversation_id)
        if (!turn.cid) await cache.fetchQuery({queryKey: [...keys, 'conversation', reply.conversation_id],
          queryFn: () => request<{messages: Turn[]; task?: Task}>(root + '/conversations/' + reply.conversation_id)})
      } catch {
        warning ||= '回复已经收到，对话记录暂未刷新；这次问答先保留在当前页面，无需重新发送。'
      }
      const saved = cache.getQueryData<{messages: Turn[]}>([...keys, 'conversation', reply.conversation_id])?.messages || []
      if (reply.history_warning || !assistantTurnStored(saved, turn.query, reply.answer, turn.afterMessageId)) {
        const local: LocalTurn = {id: turn.id, query: turn.query, reply, afterMessageId: turn.afterMessageId,
          warning: warning || '这次问答尚未显示在历史记录中，先保留在当前页面。刷新页面前请留意保存需要的内容。'}
        setLocalTurns(current => ({...current, [reply.conversation_id]: [...(current[reply.conversation_id] || []), local]}))
      }
      if (!turn.cid && selection.current === turn.selection) {
        setActiveId(reply.conversation_id)
        // Preserve text typed while waiting, and move it with this newly created conversation.
        setDrafts(current => ({...current, [reply.conversation_id]: current[''] || '', '': ''}))
      }
    },
    onError: (error, turn) => {
      const key = turn.cid || ''
      setFailed(current => ({...current, [key]: {query: turn.query, message: (error as Error).message}}))
      if (turn.fromInput) setDrafts(current => current[key] ? current : {...current, [key]: turn.query})
    },
    onSettled: () => {inFlight.current = false},
  })
  const decision = useMutation({
    mutationFn: ({task, cancel}: {task: Task; cancel: boolean}) => request<Task>(root + '/tasks/' + task.id + (cancel ? '/cancel' : '/confirm'), 'POST', {expected_version: task.version}),
    onSuccess: async task => {
      setReplies(current => ({...current, [task.conversation_id]: {...current[task.conversation_id], answer: '', conversation_id: task.conversation_id, task, intent: 'task_result', receivedAt: Date.now()}}))
      cache.setQueryData<{messages: Turn[]; task?: Task}>([...keys, 'conversation', task.conversation_id], current => current ? {...current, task} : current)
      try {await refresh(task.conversation_id)}
      catch {setSyncWarning('办理结果已收到，对话记录暂未刷新，请保留这份回执，无需重复提交。')}
    },
    onError: () => {void refresh(activeId).catch(() => undefined)},
  })
  const attachment = useMutation({
    mutationFn: async ({task, file}: {task: Task; file: File | null}) => {
      let attachmentId: string | null = null
      if (file) {
        if (!/\.(pdf|jpe?g|png)$/i.test(file.name) || file.size > 5 * 1024 * 1024 || !file.size) throw new Error('请选择5MB以内的PDF、JPG或PNG文件。')
        const body = new FormData()
        body.set('file', file)
        const proof = await request<{id: string}>('/api/v1/student/leaves/attachments', 'POST', body)
        attachmentId = proof.id
      }
      return request<Task>(root + '/tasks/' + task.id + '/attachment', 'PATCH', {expected_version: task.version, attachment_id: attachmentId})
    },
    onSuccess: async task => {
      setReplies(current => ({...current, [task.conversation_id]: {...current[task.conversation_id], answer: '', conversation_id: task.conversation_id, task, receivedAt: Date.now()}}))
      cache.setQueryData<{messages: Turn[]; task?: Task}>([...keys, 'conversation', task.conversation_id], current => current ? {...current, task} : current)
      try {await refresh(task.conversation_id)}
      catch {setSyncWarning('附件已保存到草稿，对话记录暂未刷新。核对附件和最新信息后再确认。')}
    },
    onError: () => {void refresh(activeId).catch(() => undefined)},
  })
  const messages = detail.data?.messages || []
  const ownPending = send.isPending && send.variables.cid === activeId
  const ownFailed = failed[activeId || '']
  const ownDecisionError = decision.variables?.task.conversation_id === activeId ? decision.error : undefined
  const ownAttachmentError = attachment.variables?.task.conversation_id === activeId ? attachment.error : undefined
  const question = drafts[activeId || ''] || ''
  const latest = activeId ? replies[activeId] : undefined
  const pendingRecorded = ownPending && latest?.localRequestId === send.variables.id && assistantTurnStored(messages, send.variables.query, latest.answer, send.variables.afterMessageId)
  const displayPending = ownPending && !pendingRecorded
  const task = newestAssistantTask(detail.data?.task, latest?.task, latest?.receivedAt, detail.dataUpdatedAt)
  const busy = send.isPending || decision.isPending || attachment.isPending
  const lastAssistant = messages.filter(turn => turn.role === 'assistant').at(-1)
  const activeLocalTurns = activeId
    ? (localTurns[activeId] || []).filter(turn => !detail.data || detail.isFetching || turn.reply.history_warning || !assistantTurnStored(detail.data.messages, turn.query, turn.reply.answer, turn.afterMessageId))
    : []
  const latestUnrecorded = activeLocalTurns.some(turn => turn.id === latest?.localRequestId)
  const displayTurns = orderAssistantTurns(messages, activeLocalTurns)
  const localPresentationIsCurrent = !!latest && (latestUnrecorded || latest.intent === 'task_result' || (latest.receivedAt || 0) > detail.dataUpdatedAt)
  const lastPresentation = localPresentationIsCurrent ? latest : lastAssistant?.presentation || latest
  const guiding = ['leave_create', 'feedback', 'task_result'].includes(lastPresentation?.intent || '')
  const visiblePartial = displayPending && partial?.id === send.variables.id ? partial.text : ''
  const empty = !messages.length && !ownPending && !latest && !ownFailed
  function readingPosition() {
    const element = thread.current
    if (!element) return undefined
    const responses = element.querySelectorAll<HTMLElement>('[data-assistant-response]')
    const response = responses.item(responses.length - 1)
    return {scrollTop: element.scrollTop, scrollHeight: element.scrollHeight, viewportHeight: element.clientHeight,
      responseTop: response ? response.getBoundingClientRect().top - element.getBoundingClientRect().top + element.scrollTop : undefined}
  }
  function updateReadingAction() {
    const position = readingPosition()
    setReadingAction(position ? replyReadingAction(position) : undefined)
  }
  function scrollThread(top: number) {
    if (!thread.current) return
    thread.current.scrollTop = top
    programmedScroll.current = thread.current.scrollTop
    updateReadingAction()
  }
  useLayoutEffect(() => {
    const position = readingPosition()
    if (!position) return
    const target = replyScrollTarget({...position, followReply: followReply.current})
    if (target !== undefined) scrollThread(target)
    else updateReadingAction()
  }, [activeId, detail.data, detail.isFetching, ownPending, latest, partial, ownFailed, localTurns])
  useEffect(() => {
    const element = thread.current
    if (!element) return
    const observer = new ResizeObserver(() => {
      const position = readingPosition()
      if (!position) return
      const target = replyScrollTarget({...position, followReply: followReply.current})
      if (target !== undefined) scrollThread(target)
      else updateReadingAction()
    })
    observer.observe(element)
    return () => observer.disconnect()
  }, [])
  function continueReading() {
    const position = readingPosition()
    if (!position) return
    if (readingAction === 'latest') {
      followReply.current = true
      scrollThread(replyScrollTarget({...position, followReply: true}) || 0)
    } else {
      followReply.current = false
      scrollThread(Math.min(position.scrollTop + position.viewportHeight * .8, position.scrollHeight - position.viewportHeight))
    }
  }
  function choose(id?: string) {
    if (!id && busy) return
    selection.current += 1
    setActiveId(id)
    setHistoryOpen(false)
    setHintsOpen(false)
    setSyncWarning('')
    followReply.current = true
    setReadingAction(undefined)
  }
  const sendMutate = send.mutate
  function sendQuery(query: string, fromInput = false, cid: string | null = activeId || null) {
    if (!query.trim() || busy || inFlight.current) return
    inFlight.current = true
    followReply.current = true
    setHintsOpen(false)
    setSyncWarning('')
    const id = ++requestCount.current
    setPartial({id, text: ''})
    setFailed(current => ({...current, [cid || '']: undefined}))
    if (fromInput) setDrafts(current => ({...current, [cid || '']: ''}))
    sendMutate({query: query.trim(), cid: cid || undefined, selection: selection.current, id, fromInput, afterMessageId: cid === activeId ? (messages.at(-1)?.id || 0) : 0})
  }
  useEffect(() => {
    if (!launch || consumedLaunch.current === launch.id || busy || inFlight.current) return
    if (!launch.query.trim()) return
    consumedLaunch.current = launch.id
    selection.current += 1
    inFlight.current = true
    followReply.current = true
    const id = ++requestCount.current
    const queryText = launch.query.trim()
    const currentSelection = selection.current
    queueMicrotask(() => {
      setActiveId(undefined)
      setHintsOpen(false)
      setSyncWarning('')
      setPartial({id, text: ''})
      setFailed(current => ({...current, '': undefined}))
      sendMutate({query: queryText, cid: undefined, selection: currentSelection, id, fromInput: false, afterMessageId: 0})
    })
  }, [launch, busy, sendMutate])
  function submit() {
    if (!question.trim() || busy || detail.isFetching && !!activeId) return
    sendQuery(question, true)
  }
  return <section className="stu-chat" aria-label="学生助手">
    <header className="stu-chat__toolbar">
      <div><Typography.Title level={4} style={{margin: 0}}>学生助手</Typography.Title>
        <Typography.Text type="secondary">聊聊近况，或一起把事情安排好</Typography.Text></div>
      <Space wrap size={6}><Button size="small" onClick={() => setHistoryOpen(true)}>对话记录</Button>
        <Button size="small" aria-label="我的当前情况" onClick={() => setFactsOpen(true)}>当前情况</Button>
        <Button size="small" onClick={() => setMemoriesOpen(true)}>我的记忆</Button>
        <Button size="small" disabled={busy} onClick={() => choose()}>新对话</Button></Space>
    </header>
    <div ref={thread} className="stu-chat__thread" role="log" aria-live="polite" aria-busy={ownPending} tabIndex={0}
      onWheel={() => {followReply.current = false}}
      onTouchMove={() => {followReply.current = false}}
      onKeyDown={e => {if (['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' '].includes(e.key)) followReply.current = false}}
      onScroll={e => {
        const element = e.currentTarget
        if (programmedScroll.current !== undefined && Math.abs(element.scrollTop - programmedScroll.current) < 2) programmedScroll.current = undefined
        else followReply.current = false
        updateReadingAction()
      }}>
      {detail.isFetching && activeId && <Typography.Text type="secondary">正在读取对话…</Typography.Text>}
      {empty && !detail.isFetching && <div className="stu-chat__welcome">
        <span className="student-eyebrow">你好呀，很高兴见到你</span>
        <h2>今天过得怎么样？</h2>
        <p>想聊聊近况、了解当地生活，或是有事情需要安排，都可以从这里开始。</p>
      </div>}
      {displayTurns.map(entry => entry.server ? <article data-assistant-response={entry.server.role === 'assistant' ? '' : undefined} key={'saved-' + entry.server.id} className={'stu-chat__bubble ' + (entry.server.role === 'user' ? 'is-user' : '')}>
        <span>{entry.server.role === 'user' ? '我' : '学生助手'}</span><div>{entry.server.content}</div>{entry.server.presentation?.reply_notice && <p className="stu-chat__reply-notice" role="status">{entry.server.presentation.reply_notice}</p>}<Cards cards={entry.server.presentation?.cards} presentation={entry.server.presentation} onToggle={updateReadingAction}/>
      </article> : <Fragment key={'local-' + entry.local.id}>
        <article className="stu-chat__bubble is-user"><span>我</span><div>{entry.local.query}</div></article>
        <article className="stu-chat__bubble" data-assistant-response=""><span>学生助手</span><div>{entry.local.reply.answer}</div>{entry.local.reply.reply_notice && <p className="stu-chat__reply-notice" role="status">{entry.local.reply.reply_notice}</p>}<Cards cards={entry.local.reply.cards} presentation={entry.local.reply} onToggle={updateReadingAction}/><p className="stu-chat__history-warning">{entry.local.warning}</p></article>
      </Fragment>)}
      {displayPending && <><article className="stu-chat__bubble is-user"><span>我</span><div>{send.variables.query}</div></article>
        <article className={'stu-chat__bubble' + (visiblePartial ? ' is-streaming' : '')} data-assistant-response="">
          <span>学生助手</span>{visiblePartial ? <div>{visiblePartial}</div> : <p className="stu-chat__working" role="status">正在了解你的问题…</p>}
        </article></>}
      {!ownPending && ownFailed && <div className="stu-chat__failed">
        <Alert type="warning" showIcon title="这次没有收到完整回复" description={ownFailed.message}/>
        <p>刚才发送：{ownFailed.query}</p><small>连接中断时，先核对对话记录和办理结果，避免重复操作。</small>
        <Space wrap><Button size="small" disabled={busy} onClick={() => sendQuery(ownFailed.query, question.trim() === ownFailed.query)}>重试发送</Button>
          <Button size="small" disabled={busy || !!question} onClick={() => {setDrafts(current => ({...current, [activeId || '']: ownFailed.query})); input.current?.focus()}}>{question.trim() === ownFailed.query ? '原文已在输入框' : '恢复到输入框'}</Button>
          <Button size="small" type="text" onClick={() => setFailed(current => ({...current, [activeId || '']: undefined}))}>收起提示</Button></Space>
      </div>}
      {!ownPending && !!lastPresentation?.choices?.length && <div className="stu-chat__reply-choices">{lastPresentation.choices.map(choice => <Button disabled={busy} key={choice.query} onClick={() => sendQuery(choice.query)}>{choice.label}</Button>)}</div>}
      {!ownPending && task && (guiding || !messages.length) && <StudentAssistantGuide key={task.id + ':' + task.version} task={task} busy={busy}
        send={sendQuery} decide={cancel => decision.mutate({task, cancel})} attach={file => attachment.mutate({task, file})}/>}
      {!ownPending && task && !guiding && ['collecting', 'awaiting_confirmation'].includes(task.status) && <div className="stu-chat__resume"><span>之前的{task.kind === 'leave' ? '请假' : '反馈'}信息已保留。</span><Button type="link" disabled={busy} onClick={() => sendQuery(task.kind === 'leave' ? '继续请假' : '继续准备反馈')}>继续整理</Button></div>}
    </div>
    {readingAction && <Button className="stu-chat__new-message" type="link" onClick={continueReading}>{readingAction === 'latest' ? '回到最新回复 ↓' : '继续看回复 ↓'}</Button>}
    {syncWarning && <Alert type="info" showIcon title={syncWarning} closable onClose={() => setSyncWarning('')}/>}
    {detail.error && <Alert type="warning" showIcon title="对话记录暂时无法刷新" description={(detail.error as Error).message}/>}
    {[conversations.error, ownDecisionError, ownAttachmentError].filter(Boolean).map((error, i) => <Alert key={i} type="error" showIcon title={(error as Error).message}/>)}
    <footer className="stu-chat__composer">
      {(empty || hintsOpen) && <div className="stu-chat__hints" aria-label="快捷提问">{hints.map(hint => <button key={hint} type="button" disabled={busy} onClick={() => {setDrafts(current => ({...current, [activeId || '']: hint})); input.current?.focus()}}>{hint}</button>)}</div>}
      <div className="stu-chat__input"><Input.TextArea ref={input} aria-label="输入要办的事" value={question} maxLength={1000} autoSize={{minRows: 1, maxRows: 4}} placeholder="说说今天的心情，或你想了解、安排的事情…"
        onChange={e => setDrafts(current => ({...current, [activeId || '']: e.target.value}))}
        onPressEnter={e => {if (!e.nativeEvent.isComposing && e.keyCode !== 229 && !e.shiftKey) {e.preventDefault(); submit()}}}/>
        <Button type="primary" loading={ownPending} disabled={busy || !question.trim()} onClick={submit}>发送</Button></div>
      <div className="stu-chat__composer-meta"><Typography.Text type="secondary">Enter 发送 · Shift + Enter 换行</Typography.Text>
        {!empty && <button type="button" className="stu-chat__hint-toggle" aria-expanded={hintsOpen} onClick={() => setHintsOpen(value => !value)}>{hintsOpen ? '收起快捷提问' : '快捷提问'}</button>}</div>
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
    <StudentMemory request={request} open={memoriesOpen} close={() => setMemoriesOpen(false)}/>
  </section>
}
