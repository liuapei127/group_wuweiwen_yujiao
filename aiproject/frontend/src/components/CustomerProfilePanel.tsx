import {useRef, useState} from 'react'
import {Alert, App, Button, Card, Checkbox, Descriptions, Form, Input, InputNumber, Modal, Select, Space, Table, Tag} from 'antd'
import {useMutation} from '@tanstack/react-query'
import {ErrorNotice} from './shared'

export type Request = <T>(path: string, method?: string, body?: unknown) => Promise<T>

export type CustomerFields = {
  customer_name: string | null
  nickname: string | null
  contact_info: string | null
  intended_project: string | null
  age: number | null
  education_level: string | null
  education_stage: string | null
  intended_major: string | null
}
export type CustomerProfile = CustomerFields & {version: number; website_linked?: boolean}
type Field = keyof CustomerFields
type Diff = {field: Field; current: string | number | null; proposed: string | number}
type ImportPreview = {preview_id: string; version: number; file_name: string; matches: string[]; fields: Diff[]}
type ImportInput = File | {source_id: number; file_name: string | null}
type Draft = {profile: CustomerProfile; changes: Partial<CustomerFields>}

export const customerLabels: Record<Field, string> = {
  customer_name: '姓名', nickname: '昵称', contact_info: '联系方式', intended_project: '意向项目',
  age: '年龄', education_level: '学历类别', education_stage: '在读或毕业状态', intended_major: '意向专业',
}
const projectLabels = {
  sg_junior: '新加坡初中升学', sg_senior: '新加坡高中或同等学历升学', sg_hospitality: '新加坡酒店就业班',
  sg_aviation: '新加坡航空就业班', sg_top_up: '新加坡专升本', sg_masters: '新加坡本升硕', de_vocational: '德国双元制',
}
const educationLabels = {
  junior_secondary: '初中', senior_secondary: '高中', vocational_secondary: '中职或同等学历',
  college: '大专', bachelor: '本科', postgraduate: '研究生', other: '其他',
}
const stageLabels = {enrolled: '在读', senior_year_two: '高二在读', graduated: '已毕业'}
const selectLabels: Partial<Record<Field, Record<string, string>>> = {
  intended_project: projectLabels, education_level: educationLabels, education_stage: stageLabels,
}
const fieldNames = Object.keys(customerLabels) as Field[]

export function customerValue(field: Field, value: string | number | null | undefined) {
  if (value === undefined || value === null || value === '') return field === 'customer_name' ? '' : '未填写'
  if (field === 'age') return value + ' 岁'
  return selectLabels[field]?.[String(value)] || String(value)
}

export function useCustomerEditor(profile: CustomerProfile | undefined, request: Request, endpoint: string, onSaved: () => void) {
  const [draft, setDraft] = useState<Draft>()
  const {message} = App.useApp()
  const save = useMutation({
    mutationFn: (current: Draft) => request<CustomerProfile>(endpoint, 'PATCH', {
      ...current.changes, expected_version: current.profile.version,
    }),
    onSuccess: () => {
      setDraft(undefined)
      onSaved()
      void message.success('客户资料已保存')
    },
  })
  return {
    draft, save,
    edit() {
      if (profile) {
        save.reset()
        setDraft({profile, changes: {}})
      }
    },
    cancel() {
      setDraft(undefined)
      save.reset()
    },
    change(fields: Partial<CustomerFields>) {
      const normalized = Object.fromEntries(Object.entries(fields).map(([field, value]) => [field, value ?? null]))
      setDraft(current => current && {...current, changes: {...current.changes, ...normalized}})
    },
  }
}

export function useCustomerImport(request: Request, endpoint: string, onSaved: () => void) {
  const [source, setSource] = useState<ImportInput>()
  const [selected, setSelected] = useState<Field[]>([])
  const {message} = App.useApp()
  const preview = useMutation({
    mutationFn: (input: ImportInput) => {
      if (!(input instanceof File)) {
        return request<ImportPreview>(endpoint + '/materials/' + input.source_id + '/imports/preview', 'POST')
      }
      if (input.size > 10 * 1024 * 1024) throw new Error('文件不能超过 10 MB')
      const body = new FormData()
      body.append('file', input)
      return request<ImportPreview>(endpoint + '/imports/preview', 'POST', body)
    },
    onSuccess: data => setSelected(data.fields.map(row => row.field)),
  })
  const confirm = useMutation({
    mutationFn: (data: ImportPreview) => request<CustomerProfile>(endpoint + '/imports/confirm', 'POST', {
      preview_id: data.preview_id, expected_version: data.version, fields: selected,
      ...(source && !(source instanceof File) ? {source_id: source.source_id} : {}),
    }),
    onSuccess: () => {
      setSource(undefined)
      preview.reset()
      onSaved()
      void message.success('资料已导入')
    },
  })
  const working = preview.isPending || confirm.isPending
  return {
    source, selected, setSelected, preview, confirm, working,
    begin(input: ImportInput) {
      if (working) return
      confirm.reset()
      preview.reset()
      setSelected([])
      setSource(input)
      preview.mutate(input)
    },
    close() {
      if (working) return
      setSource(undefined)
      preview.reset()
      confirm.reset()
    },
  }
}

export function CustomerImportDialog({importer, onChooseFile}: {
  importer: ReturnType<typeof useCustomerImport>; onChooseFile?: () => void
}) {
  const {source, selected, setSelected, preview, confirm, working} = importer
  const fileName = source instanceof File ? source.name : source?.file_name || '文字资料'
  const data = preview.data
  return <Modal title={data ? '确认导入客户资料' : source instanceof File ? '上传资料' : '识别客户资料'} open={!!source}
    onCancel={importer.close} closable={!working} keyboard={!working} mask={{closable: !working}}
    width={690} footer={<Space wrap>
      <Button disabled={working} onClick={importer.close}>取消</Button>
      {data ? <Button type="primary" disabled={!selected.length} loading={confirm.isPending}
        onClick={() => confirm.mutate(data)}>确认保存</Button>
        : onChooseFile && <Button type="primary" disabled={working} onClick={onChooseFile}>重新选择文件</Button>}
    </Space>}>
    <Space orientation="vertical" size="middle" style={{width: '100%'}}>
      <div className="customer-document"><strong>{fileName}</strong></div>
      {preview.isPending && <Alert title="正在识别资料并核对归属" type="info" showIcon/>}
      <ErrorNotice error={preview.error || confirm.error}/>
      {data && <>
        <Space wrap>{data.matches.map(name => <Tag key={name} color="success">{name}一致</Tag>)}</Space>
        <Table<Diff> rowKey="field" size="small" pagination={false} dataSource={data.fields} columns={[
          {title: '选择', width: 58, render: (_, row) => <Checkbox aria-label={'更新' + customerLabels[row.field]}
            checked={selected.includes(row.field)} disabled={confirm.isPending} onChange={event => setSelected(current =>
              event.target.checked ? [...current, row.field] : current.filter(field => field !== row.field))}/>},
          {title: '字段', render: (_, row) => customerLabels[row.field]},
          {title: '当前资料', render: (_, row) => customerValue(row.field, row.current)},
          {title: '文件提取值', render: (_, row) => customerValue(row.field, row.proposed)},
        ]}/>
      </>}
    </Space>
  </Modal>
}

export function CustomerProfilePanel({profile, request, endpoint, importEndpoint = endpoint, editor, canWrite, onSaved}: {
  profile: CustomerProfile
  request: Request
  endpoint: string
  importEndpoint?: string
  editor: ReturnType<typeof useCustomerEditor>
  canWrite: boolean
  onSaved: () => void
}) {
  const filePicker = useRef<HTMLInputElement>(null)
  const importer = useCustomerImport(request, importEndpoint, onSaved)

  const {draft, save} = editor
  const fields = fieldNames.filter(name => name !== 'nickname' || profile.website_linked !== false)
  const working = importer.working
  const pickFile = () => filePicker.current?.click()

  return <Card title="客户资料" extra={canWrite && !draft && <Space wrap>
    <Button disabled={working} onClick={editor.edit}>手动编辑</Button>
    <Button type="primary" disabled={working} onClick={pickFile}>上传资料</Button>
  </Space>}>
    <input type="file" hidden ref={filePicker} aria-label="选择客户资料" accept=".txt,.csv,.xls,.xlsx,.pdf"
      onChange={event => {
        const file = event.currentTarget.files?.[0]
        event.currentTarget.value = ''
        if (!file || working || draft) return
        importer.begin(file)
      }}/>
    {draft ? <>
      <ErrorNotice error={save.error}/>
      <Form<CustomerFields> layout="vertical" initialValues={draft.profile} disabled={save.isPending}
        onValuesChange={editor.change}
        onFinish={() => save.mutate(draft)}>
        <div className="customer-detail-fields">
          {fields.map(field => {
            const choices = selectLabels[field]
            return <Form.Item key={field} name={field} label={customerLabels[field]}>
              {choices ? <Select allowClear options={Object.entries(choices).map(([value, label]) => ({value, label}))}/>
                : field === 'age' ? <InputNumber min={0} max={120} precision={0} style={{width: '100%'}}/>
                  : <Input maxLength={field === 'contact_info' || field === 'intended_major' ? 128 : 64}/>}
            </Form.Item>
          })}
        </div>
        <Space wrap>
          <Button disabled={save.isPending} onClick={editor.cancel}>取消编辑</Button>
          <Button type="primary" htmlType="submit" loading={save.isPending}>保存资料</Button>
        </Space>
      </Form>
    </> : <Descriptions column={{xs: 1, sm: 2, lg: 2}} items={fields.map(field => ({
      key: field, label: customerLabels[field], children: customerValue(field, profile[field]),
    }))}/>}
    <CustomerImportDialog importer={importer} onChooseFile={pickFile}/>
  </Card>
}
