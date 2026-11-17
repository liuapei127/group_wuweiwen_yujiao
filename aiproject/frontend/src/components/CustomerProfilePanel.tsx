import {useEffect, useRef, useState} from 'react'
import {Alert, App, Button, Card, Checkbox, Descriptions, Form, Input, InputNumber, Modal, Select, Space, Table, Tag, Typography} from 'antd'
import {useMutation} from '@tanstack/react-query'
import {ErrorNotice} from './shared'

export type Request = <T>(path: string, method?: string, body?: unknown, onText?: (text: string) => void) => Promise<T>

export function usePortraitUpdates(request: Request, endpoint: string, version: number | undefined, onChanged: () => Promise<unknown>) {
  const handlers = useRef({request, onChanged})
  useEffect(() => {handlers.current = {request, onChanged}}, [request, onChanged])
  useEffect(() => {
    if (version === undefined) return
    let stopped = false
    let retry: number | undefined
    async function subscribe() {
      let delay = 250
      if (!document.hidden) {
        try {
          const separator = endpoint.includes('?') ? '&' : '?'
          const event = await handlers.current.request<{changed?: boolean}>(endpoint + separator + 'watch_version=' + version, 'GET', undefined, () => {})
          if (stopped) return
          if (event.changed) {
            await handlers.current.onChanged()
            delay = 1000
          } else if (event.changed !== false) {
            await handlers.current.onChanged()
            delay = 2000
          }
        } catch {
          if (!stopped) await handlers.current.onChanged()
          delay = 2000
        }
      } else {
        delay = 2000
      }
      if (!stopped) retry = window.setTimeout(() => void subscribe(), delay)
    }
    void subscribe()
    return () => {
      stopped = true
      window.clearTimeout(retry)
    }
  }, [endpoint, version])
}

export type CustomerFields = {
  customer_name: string | null
  nickname: string | null
  contact_info: string | null
  intended_project: string | null
  age: number | null
  education_level: string | null
  education_stage: string | null
  intended_major: string | null
  domestic_scope: string | null
  family_finance: string | null
  further_study: string | null
  employment: string | null
  admission: string | null
  overseas_intent: string | null
  policy_attention: string | null
  immigration: string | null
  skill: string | null
  german: string | null
  family_support: string | null
  cost_sense: string | null
  learning_attitude: string | null
  gender: string | null
  core_demand: string | null
  language_ability: string | null
  hands_on: string | null
  logical_thinking: string | null
}
type FieldValue = string | number | Record<string, number> | null
type Evidence = {
  source?: string; updated_at?: string; confirmed?: boolean
  conflicts?: {value: FieldValue; source: string; updated_at: string}[]
}
export type CustomerProfile = CustomerFields & {
  version: number; website_linked?: boolean
  pending_customer?: boolean
  screening_input?: Record<string, unknown>[]
  tag_weight?: Record<string, number>
  portrait_updated_at?: string
  portrait_evidence?: Partial<Record<keyof CustomerFields, Evidence>>
}
type Field = keyof CustomerFields | 'tag_weight'
type Diff = {field: Field; current: FieldValue; proposed: FieldValue}
type ImportPreview = {preview_id: string; version: number; file_name: string; matches: string[]; fields: Diff[]}
type ImportInput = File | {source_id: number; file_name: string | null}
type Draft = {profile: CustomerProfile; changes: Partial<CustomerFields>}

export const customerLabels: Record<Field, string> = {
  customer_name: '姓名', nickname: '昵称', contact_info: '联系方式', intended_project: '意向项目',
  age: '年龄', education_level: '学历类别', education_stage: '在读或毕业状态', intended_major: '意向专业',
  domestic_scope: '国内范围', family_finance: '家庭经济状况', further_study: '升学需求',
  employment: '就业需求 / 就业导向', admission: '入学能力', overseas_intent: '留学意愿',
  policy_attention: '政策关注度', immigration: '移民需求', skill: '技能需求', german: '德语水平',
  family_support: '家庭支持', cost_sense: '经济理性', learning_attitude: '学习态度',
  gender: '性别', core_demand: '核心需求', language_ability: '语言能力', hands_on: '动手能力', logical_thinking: '逻辑思维',
  tag_weight: '标签权重',
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
const profileSections: {title: string; fields: (keyof CustomerFields)[]}[] = [
  {title: '基本信息', fields: ['customer_name', 'nickname', 'contact_info', 'age', 'gender', 'domestic_scope']},
  {title: '教育与能力', fields: ['education_level', 'education_stage', 'language_ability', 'admission', 'skill', 'hands_on', 'logical_thinking', 'learning_attitude']},
  {title: '留学意向与需求', fields: ['intended_project', 'intended_major', 'overseas_intent', 'core_demand', 'further_study', 'employment', 'immigration', 'policy_attention']},
  {title: '家庭与预算', fields: ['family_finance', 'family_support', 'cost_sense']},
]

export function customerValue(field: Field, value: FieldValue | undefined) {
  if (value === undefined || value === null || value === '') return field === 'customer_name' ? '' : '未填写'
  if (typeof value === 'object') return JSON.stringify(value)
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
  const visible = (name: Field) => name !== 'nickname' || profile.website_linked !== false
  const working = importer.working
  const pickFile = () => filePicker.current?.click()
  const control = (field: Field) => {
    const choices = selectLabels[field]
    if (choices) return <Select allowClear options={Object.entries(choices).map(([value, label]) => ({value, label}))}/>
    if (field === 'age') return <InputNumber min={0} max={120} precision={0} style={{width: '100%'}}/>
    if (field === 'language_ability') return <Input.TextArea maxLength={1000} autoSize={{minRows: 2}} placeholder="每行填写一种语言及水平或成绩"/>
    const wide = field === 'contact_info' || field === 'intended_major' || field in {
      domestic_scope: 1, family_finance: 1, further_study: 1, employment: 1, admission: 1,
      overseas_intent: 1, policy_attention: 1, immigration: 1, skill: 1, german: 1,
      family_support: 1, cost_sense: 1, learning_attitude: 1, gender: 1, core_demand: 1, language_ability: 1, hands_on: 1, logical_thinking: 1,
    }
    return <Input maxLength={wide ? 128 : 64}/>
  }

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
      {draft.profile.version !== profile.version && <Alert type="warning" showIcon title="画像有新版本，请取消后重新核对资料"/>}
      <Form<CustomerFields> layout="vertical" initialValues={draft.profile} disabled={save.isPending}
        onValuesChange={editor.change}
        onFinish={() => save.mutate(draft)}>
        <div className="customer-detail-fields">
          {profileSections.map(section => <div key={section.title} style={{display: 'contents'}}>
            <Typography.Title level={5} className="customer-portrait-title">{section.title}</Typography.Title>
            {section.fields.filter(visible).map(field => <Form.Item key={field} name={field} label={customerLabels[field]}>
              {control(field)}
            </Form.Item>)}
          </div>)}
        </div>
        <Space wrap>
          <Button disabled={save.isPending} onClick={editor.cancel}>取消编辑</Button>
          <Button type="primary" htmlType="submit" loading={save.isPending} disabled={draft.profile.version !== profile.version}>保存资料</Button>
        </Space>
      </Form>
    </> : profileSections.map(section => <Descriptions key={section.title} title={section.title}
      column={{xs: 1, sm: 2, lg: 2}} items={section.fields.filter(visible).map(field => ({
        key: field, label: customerLabels[field],
        children: <span style={{whiteSpace: 'pre-line'}}>{customerValue(field, profile[field])}</span>,
      }))}/>)}
    <CustomerImportDialog importer={importer} onChooseFile={pickFile}/>
  </Card>
}

const evidenceLabels: Record<string, string> = {
  customer_chat: '客服对话', visitor_material: '游客提交材料', advisor_import: '顾问导入',
  visitor_import: '游客导入', advisor_edit: '顾问编辑', visitor_edit: '游客编辑',
}

export function CustomerPortraitInput({profile, snapshot, snapshotVersion}: {
  profile: CustomerProfile; snapshot?: Record<string, unknown>[]; snapshotVersion?: number
}) {
  if (!profile.screening_input) return null
  const current = JSON.stringify(profile.screening_input, null, 2)
  const evidence = Object.entries(profile.portrait_evidence || {})
  return <Card title="用户画像与研判输入" extra={<Typography.Text type="secondary">版本 {profile.version}</Typography.Text>}>
    {profile.portrait_updated_at && <Typography.Paragraph type="secondary">
      最近更新 <time>{profile.portrait_updated_at.replace('T', ' ')}</time>
    </Typography.Paragraph>}
    <Typography.Paragraph copyable={{text: current, tooltips: ['复制研判输入', '已复制']}}>
      本次研判使用的画像
    </Typography.Paragraph>
    <pre aria-label="当前研判输入" tabIndex={0} style={{overflow: 'auto', maxHeight: 560, background: '#f5f8f7', padding: 16}}>{current}</pre>
    {!!evidence.length && <details>
      <summary>查看资料来源与待核对信息</summary>
      {evidence.map(([field, item]) => <div key={field}>
        <strong>{customerLabels[field as Field] || field}</strong>
        {item.source && <> · {evidenceLabels[item.source] || item.source} · {item.confirmed ? '已确认' : '待核对'}</>}
        {item.updated_at && <> · {item.updated_at}</>}
        {item.conflicts?.map(candidate => <div key={candidate.updated_at + candidate.source + candidate.value}>
          待核对：{customerValue(field as Field, candidate.value)}（{evidenceLabels[candidate.source] || candidate.source}）
        </div>)}
      </div>)}
    </details>}
    {snapshot && <details>
      <summary>查看上次研判的输入快照（版本 {snapshotVersion}）</summary>
      <pre aria-label="上次研判输入" tabIndex={0} style={{overflow: 'auto', maxHeight: 560}}>{JSON.stringify(snapshot, null, 2)}</pre>
    </details>}
  </Card>
}
