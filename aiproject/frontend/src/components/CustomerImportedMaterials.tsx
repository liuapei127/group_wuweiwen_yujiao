import {useEffect, useState} from 'react'
import {Alert, Button, Card, Modal, Space, Table, Tag, Typography} from 'antd'
import {useQuery} from '@tanstack/react-query'
import {ApiError, getToken, refreshSession} from '../lib/api'
import {ErrorNotice, Value} from './shared'
import type {Request} from './CustomerProfilePanel'

export type ImportedMaterial = {id: number; file_name: string | null; create_time: string}
type MaterialDetails = {
  source_id: number; file_name: string | null; raw_content: string | null; has_attachment: boolean
}
type Attachment = {url?: string; loading?: boolean; error?: Error}

async function readAttachment(path: string, token: string | undefined, signal: AbortSignal): Promise<Blob> {
  let currentToken = token ?? getToken()
  const send = () => fetch(path, {headers: {Authorization: 'Bearer ' + currentToken}, signal})
  let response = await send()
  if (response.status === 401 && token === undefined && await refreshSession()) {
    currentToken = getToken()
    response = await send()
  }
  if (!response.ok) {
    if (response.status === 401 && token === undefined) window.dispatchEvent(new Event('ent-auth-expired'))
    const data = await response.json().catch(() => ({}))
    throw new ApiError(typeof data.detail === 'string' ? data.detail : '原件读取失败，请稍后重试', response.status)
  }
  const blob = await response.blob()
  if (token === undefined && getToken() !== currentToken) throw new Error('登录身份已变更，请重新打开资料')
  return blob
}

export function CustomerImportedMaterials({imports, request, endpoint, scope, token}: {
  imports?: ImportedMaterial[]; request: Request; endpoint: string; scope: string | number | undefined; token?: string
}) {
  const [selected, setSelected] = useState<ImportedMaterial>()
  const [attachmentState, setAttachmentState] = useState<Attachment & {id?: number}>({})
  const selectedId = selected?.id
  const details = useQuery({
    queryKey: ['customer-import-details', scope, endpoint, selectedId], enabled: !!selectedId,
    queryFn: () => request<MaterialDetails>(endpoint + '/imports/' + selectedId!), staleTime: 0,
  })
  const hasAttachment = details.data?.has_attachment
  const attachment: Attachment = !selectedId || !hasAttachment
    ? {}
    : attachmentState.id === selectedId
      ? attachmentState
      : {loading: true}
  useEffect(() => {
    if (!selectedId || !hasAttachment) return
    const controller = new AbortController()
    let active = true
    let url: string | undefined
    void readAttachment(endpoint + '/imports/' + selectedId + '/attachment', token, controller.signal)
      .then(blob => {
        if (active) {
          url = URL.createObjectURL(blob)
          setAttachmentState({id: selectedId, url})
        }
      }).catch((error: Error) => {
        if (active) setAttachmentState({id: selectedId, error})
      })
    return () => {
      active = false
      controller.abort()
      if (url) URL.revokeObjectURL(url)
    }
  }, [endpoint, selectedId, hasAttachment, token])

  if (!imports?.length) return null
  const fileName = details.data?.file_name || selected?.file_name || '文字资料'
  return <>
    <Card title="已导入资料">
      <Table<ImportedMaterial> rowKey="id" size="small" pagination={false} dataSource={imports} columns={[
        {title: '文件', render: (_, row) => <Button type="link" style={{paddingInline: 0, whiteSpace: 'normal', textAlign: 'left'}}
          onClick={() => setSelected(row)}>{row.file_name || '文字资料'}</Button>},
        {title: '保存时间', dataIndex: 'create_time', render: value => <Value value={value}/>},
        {title: '状态', render: () => <Tag color="success">资料已更新</Tag>},
      ]}/>
    </Card>
    <Modal title={fileName} open={!!selected} onCancel={() => setSelected(undefined)} width={900} footer={null}>
      <Space orientation="vertical" size="middle" style={{width: '100%'}}>
        <ErrorNotice error={details.error || attachment.error}/>
        {details.isPending && <Typography.Text>正在读取资料…</Typography.Text>}
        {attachment.loading && <Typography.Text>正在读取原件…</Typography.Text>}
        {attachment.url && <>
          <Button href={attachment.url} download={fileName}>下载原件</Button>
          {fileName.toLowerCase().endsWith('.pdf') && <iframe title="资料原件" src={attachment.url}
            style={{width: '100%', height: '65vh', border: 0}}/>}
        </>}
        {details.data?.raw_content && <Typography.Paragraph style={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>
          {details.data.raw_content}
        </Typography.Paragraph>}
        {details.data && !details.data.has_attachment && !details.data.raw_content &&
          <Alert type="info" showIcon title="这份历史资料未保留原件和正文"/>}
      </Space>
    </Modal>
  </>
}
