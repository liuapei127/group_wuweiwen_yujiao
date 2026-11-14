import {useRef, useState} from 'react'
import {Alert, App, Button, Card, Drawer, Form, Input, Space, Table, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ErrorNotice, PageTitle} from '../components/shared'
import {api, query} from '../lib/api'
import {
  HistoryPaging, ScreeningForm, beijingTime, pageSize, screeningStatuses,
  type ScreeningResult, type SourceDetails,
} from './VisitorIntake'

const endpoint = '/api/v1/profile'
type AdvisorSource = {source_id: number; file_name: string | null; submitted_at: string; screening: ScreeningResult | null}

export function ProfileScreening() {
  const {can} = useAuth()
  return <>
    <PageTitle title="客户研判" description="上传顾问收集的客户资料，查看规则初筛，并运行 Dify 研判建议。"/>
    <Card>
      <AdvisorMaterials canWrite={can('crm:write')}/>
    </Card>
  </>
}

function AdvisorMaterials({canWrite}: {canWrite: boolean}) {
  const {user} = useAuth()
  const {message} = App.useApp()
  const cache = useQueryClient()
  const file = useRef<HTMLInputElement>(null)
  const [form] = Form.useForm<{raw_content?: string}>()
  const [before, setBefore] = useState<number>()
  const [active, setActive] = useState<number>()
  const scope = [user?.id, 'advisor-materials']
  const list = useQuery({
    queryKey: [...scope, before],
    queryFn: () => api<AdvisorSource[]>(endpoint + query({before_id: before, limit: pageSize})),
  })
  const upload = useMutation({
    mutationFn: (values: {raw_content?: string}) => {
      const body = new FormData()
      const attachment = file.current?.files?.[0]
      const extension = attachment?.name.split('.').at(-1)?.toLowerCase()
      const types: Record<string, string> = {pdf: 'pdf_resume', xls: 'excel', xlsx: 'excel', csv: 'import'}
      body.append('source_type', types[extension ?? ''] ?? 'text')
      if (values.raw_content?.trim()) body.append('raw_content', values.raw_content.trim())
      if (attachment) body.append('file', attachment)
      return api<{source_id: number}>(endpoint + '/upload', {method: 'POST', body})
    },
    onSuccess: item => {
      form.resetFields()
      if (file.current) file.current.value = ''
      setBefore(undefined)
      setActive(item.source_id)
      void cache.invalidateQueries({queryKey: scope})
      void message.success('客户资料已提交')
    },
  })
  return <Space orientation="vertical" style={{width: '100%'}}>
    {canWrite && <Form form={form} layout="vertical" onFinish={values => upload.mutate(values)}>
      <Form.Item name="raw_content" label="客户资料说明">
        <Input.TextArea maxLength={16000} placeholder="可粘贴顾问收集的单个客户资料"/>
      </Form.Item>
      <Form.Item label="附件" htmlFor="advisor-material-file">
        <input id="advisor-material-file" ref={file} type="file" accept=".txt,.csv,.pdf,.xls,.xlsx"/>
      </Form.Item>
      <Button type="primary" htmlType="submit" loading={upload.isPending}>提交客户资料</Button>
    </Form>}
    <ErrorNotice error={upload.error || list.error}/>
    <Table<AdvisorSource> rowKey="source_id" dataSource={list.data ?? []} loading={list.isFetching} pagination={false} columns={[
      {title: '客户资料', render: (_, row) => row.file_name || '文字资料'},
      {title: '上传时间（北京时间）', dataIndex: 'submitted_at', render: beijingTime},
      {title: '初筛结果', render: (_, row) => row.screening ? screeningStatuses[row.screening.status] : '待研判'},
      {title: '操作', render: (_, row) => <Button type="link" onClick={() => setActive(row.source_id)}>查看与研判</Button>},
    ]}/>
    <HistoryPaging before={before} count={list.data?.length ?? 0} reset={() => setBefore(undefined)}
      next={() => setBefore(list.data?.at(-1)?.source_id)}/>
    <Drawer title="客户资料研判" open={active !== undefined} onClose={() => setActive(undefined)} size="large">
      {active !== undefined && <AdvisorReview key={active} id={active} canWrite={canWrite}
        onSaved={() => void cache.invalidateQueries({queryKey: scope})}/>}
    </Drawer>
  </Space>
}

function AdvisorReview({id, canWrite, onSaved}: {id: number; canWrite: boolean; onSaved: () => void}) {
  const {user} = useAuth()
  const path = endpoint + '/' + id
  const details = useQuery({queryKey: [user?.id, 'advisor-material', id], queryFn: () => api<SourceDetails>(path)})
  const preview = useMutation({mutationFn: () => api<{match_reason: string}>(path + '/dify-preview', {method: 'POST', timeout: 60000})})
  return <Space orientation="vertical" style={{width: '100%'}}>
    <ErrorNotice error={details.error || preview.error}/>
    {details.data && <>
      <Typography.Paragraph style={{whiteSpace: 'pre-wrap'}}>{details.data.raw_content}</Typography.Paragraph>
      <Button loading={preview.isPending} onClick={() => preview.mutate()}>运行 Dify 研判</Button>
      {preview.data && <Alert type="info" title="Dify 研判建议" description={preview.data.match_reason}/>}
      <ScreeningForm initial={details.data.screening_input} result={details.data.screening} enabled={canWrite}
        path={path + '/analyze'} onSaved={() => {void details.refetch(); onSaved()}}/>
    </>}
  </Space>
}
