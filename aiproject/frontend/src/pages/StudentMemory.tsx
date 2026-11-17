import {useState} from 'react'
import {Alert, Button, Card, Drawer, Empty, Input, Modal, Space, Tag, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'

type Request = <T>(path: string, method?: string, body?: unknown) => Promise<T>
type Memory = {id: number; memory: string; kind: 'name' | 'preference' | 'self_report' | 'legacy'; create_time: string; update_time: string; version: string}
type Page = {items: Memory[]; has_more: boolean; storage: 'local'; notes: string}
const endpoint = '/api/v1/student/assistant/memories'
const keys = ['visitor', 'student', 'memories']
const labels = {name: '称呼', preference: '偏好', self_report: '你的自述', legacy: '历史记忆'}

export function StudentMemory({request, open, close}: {request: Request; open: boolean; close: () => void}) {
  const cache = useQueryClient()
  const [before, setBefore] = useState<number>()
  const [editing, setEditing] = useState<Memory>()
  const [text, setText] = useState('')
  const [modal, holder] = Modal.useModal()
  const records = useQuery({queryKey: [...keys, before], enabled: open,
    queryFn: () => request<Page>(endpoint + '?limit=20' + (before ? '&before_id=' + before : '')),
    staleTime: 0,
  })
  const change = useMutation({
    mutationFn: ({row, memory}: {row: Memory; memory?: string}) => request(endpoint + '/' + row.id, memory === undefined ? 'DELETE' : 'PATCH',
      {expected_version: row.version, ...(memory === undefined ? {} : {memory})}),
    onSuccess: async () => {setEditing(undefined); await cache.invalidateQueries({queryKey: keys})},
    onError: () => {void cache.invalidateQueries({queryKey: keys})},
  })
  const clear = useMutation({mutationFn: () => request(endpoint, 'DELETE'), onSuccess: async () => {
    setEditing(undefined); setBefore(undefined); await cache.invalidateQueries({queryKey: keys})
  }})
  const busy = change.isPending || clear.isPending
  function remove(row: Memory) {
    modal.confirm({title: '删除这条记忆？', content: '删除后，新对话不再将它作为长期记忆使用。历史对话和学籍仍保留，已有会话中仍可能看到原文。',
      okText: '删除记忆', cancelText: '取消', okButtonProps: {danger: true}, onOk: () => change.mutateAsync({row})})
  }
  return <Drawer title="我的对话记忆" open={open} onClose={close} size="large" className="stu-memory">
    {holder}
    <Alert type="info" showIcon title="这些是交流中记下的内容，可以由你纠正或删除。"
      description="记忆按当前账号保存在本机，用于交流参考。它不会修改学籍、申请进度，也不能代替你的办理确认。"/>
    <div className="stu-memory__tools"><Button loading={records.isFetching} onClick={() => void records.refetch()}>刷新记忆</Button>
      <Button danger disabled={busy || !records.data?.items.length} onClick={() => modal.confirm({
        title: '清空全部对话记忆？', content: '将删除当前账号的全部长期记忆。历史聊天、学籍和业务记录仍保留，已有会话中仍可能看到原文；新对话不再召回这些长期记忆。',
        okText: '清空全部记忆', cancelText: '保留记忆', okButtonProps: {danger: true}, onOk: () => clear.mutateAsync(),
      })}>清空全部记忆</Button></div>
    {[records.error, change.error, clear.error].filter(Boolean).map((error, i) => <Alert key={i} showIcon type="error" title={(error as Error).message}/>)}
    {records.data?.notes && <Typography.Paragraph type="secondary">{records.data.notes}</Typography.Paragraph>}
    {!records.isPending && !records.data?.items.length && <Empty description={before ? '这一页已没有记忆，可以返回最新查看' : '还没有需要长期保留的记忆'}/>}
    {records.data?.items.map(row => <Card className="stu-memory__item" key={row.id} size="small"
      title={<Tag>{labels[row.kind] || labels.legacy}</Tag>}
      extra={<small>更新：{row.update_time.slice(0, 16).replace('T', ' ')}（北京时间）</small>}>
      {editing?.id === row.id ? <>
        <Input.TextArea aria-label="纠正记忆内容" value={text} maxLength={2000} autoSize={{minRows: 2, maxRows: 6}} disabled={busy} onChange={e => setText(e.target.value)}/>
        <Space style={{marginTop: 12}}><Button type="primary" disabled={busy || !text.trim()} loading={change.isPending}
          onClick={() => change.mutate({row: editing, memory: text.trim()})}>保存纠正</Button><Button disabled={busy} onClick={() => setEditing(undefined)}>取消</Button></Space>
      </> : <>
        <p className="stu-memory__content">{row.memory}</p>
        <Space><Button disabled={busy} onClick={() => {setEditing(row); setText(row.memory); change.reset()}}>纠正内容</Button>
          <Button danger type="text" disabled={busy} onClick={() => remove(row)}>删除这条</Button></Space>
      </>}
    </Card>)}
    <Space className="stu-memory__pager"><Button disabled={!before || busy || records.isFetching} onClick={() => setBefore(undefined)}>返回最新</Button>
      <Button disabled={!records.data?.has_more || busy || records.isFetching} onClick={() => setBefore(records.data?.items.at(-1)?.id)}>查看更早</Button></Space>
  </Drawer>
}
