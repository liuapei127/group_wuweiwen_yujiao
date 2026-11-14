import {useState} from 'react'
import {App, Button, Card, Empty, Form, Input, InputNumber, Modal, Space, Spin, Switch, Table, Tag, Typography} from 'antd'
import {PlusOutlined} from '@ant-design/icons'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {ErrorNotice, PageTitle} from '../components/shared'
import {api} from '../lib/api'
import {websiteContentQueryKey, type WebsiteCard, type WebsiteSection} from '../lib/websiteContent'

type Publication = {title: string; sort_order: number; published: boolean}
type ManagedCard = WebsiteCard & Publication
type ManagedSection = WebsiteSection & Publication & {cards: ManagedCard[]}
type EditTarget = {section?: ManagedSection; isCard: false} | {section: ManagedSection; card?: ManagedCard; isCard: true}
type FormValues = Publication & {content?: string}

const endpoint = '/api/v1/enterprise/website-content'

export function WebsiteContent() {
  const {user} = useAuth()
  const cache = useQueryClient()
  const {message} = App.useApp()
  const [form] = Form.useForm<FormValues>()
  const [target, setTarget] = useState<EditTarget>()
  const key = [user?.id, 'managed-website-content']
  const sections = useQuery({queryKey: key, queryFn: () => api<ManagedSection[]>(endpoint)})
  const save = useMutation({
    mutationFn: ({edit, values}: {edit: EditTarget; values: FormValues}) => {
      const path = edit.isCard
        ? endpoint + '/' + edit.section.id + '/cards' + (edit.card ? '/' + edit.card.id : '')
        : endpoint + (edit.section ? '/' + edit.section.id : '')
      const method = (edit.isCard ? edit.card : edit.section) ? 'PUT' : 'POST'
      return api(path, {method, body: values})
    },
    onSuccess: async () => {
      await Promise.all([
        cache.invalidateQueries({queryKey: key}),
        cache.invalidateQueries({queryKey: websiteContentQueryKey}),
      ])
      setTarget(undefined)
      void message.success('已保存')
    },
  })

  function edit(next: EditTarget) {
    const record = next.isCard ? next.card : next.section
    save.reset()
    setTarget(next)
    form.setFieldsValue({
      title: record?.title || '',
      sort_order: record?.sort_order ?? (next.isCard ? (next.section.cards.length) * 10 + 10 : 30),
      published: record?.published ?? false,
      content: next.isCard ? next.card?.content || '' : undefined,
    })
  }

  return <>
    <PageTitle title="官网内容管理" description="编辑首页的栏目和卡片。已发布的内容会在官网显示。"
      extra={<>
        <Button href="/website" target="_blank" rel="noopener noreferrer">查看官网</Button>
        <Button type="primary" icon={<PlusOutlined/>} onClick={() => edit({isCard: false})}>新增栏目</Button>
      </>}/>
    <ErrorNotice error={sections.error}/>
    {sections.isPending ? <Spin/> : !sections.error && !sections.data?.length && <Empty description="暂无栏目"/>}
    <Space orientation="vertical" size="middle" style={{width: '100%'}}>
      {sections.data?.map(section => <Card key={section.id} title={<Space wrap>
        <span>{section.title}</span><Tag color={section.published ? 'green' : undefined}>{section.published ? '已发布' : '未发布'}</Tag>
        <Typography.Text type="secondary">排序 {section.sort_order}</Typography.Text>
      </Space>} extra={<Space wrap>
        <Button onClick={() => edit({section, isCard: false})}>编辑栏目</Button>
        <Button icon={<PlusOutlined/>} onClick={() => edit({section, isCard: true})}>添加卡片</Button>
      </Space>}>
        <Table<ManagedCard> rowKey="id" dataSource={section.cards} size="small" scroll={{x: 640}}
          pagination={section.cards.length > 10 ? {pageSize: 10} : false}
          locale={{emptyText: '暂无卡片'}} columns={[
            {title: '标题', dataIndex: 'title', width: 180},
            {title: '正文', dataIndex: 'content', ellipsis: true},
            {title: '排序', dataIndex: 'sort_order', width: 75},
            {title: '状态', width: 108, render: (_, row) => <Tag color={row.published ? 'green' : undefined}>
              {row.published ? '已发布' : '未发布'}
            </Tag>},
            {title: '操作', width: 80, render: (_, card) => <Button type="link" onClick={() => edit({section, card, isCard: true})}>编辑</Button>},
          ]}/>
      </Card>)}
    </Space>
    <Modal
      title={target?.isCard ? (target.card ? '编辑卡片' : '添加卡片') : (target?.section ? '编辑栏目' : '新增栏目')}
      open={!!target} onCancel={() => setTarget(undefined)} onOk={() => form.submit()}
      confirmLoading={save.isPending} closable={!save.isPending} mask={{closable: !save.isPending}}
      cancelButtonProps={{disabled: save.isPending}} okText="保存" okButtonProps={{'aria-label': '保存官网内容'}} forceRender
    >
      <ErrorNotice error={save.error}/>
      <Form form={form} layout="vertical" disabled={save.isPending} onFinish={values => {
        if (target) save.mutate({edit: target, values})
      }}>
        <Form.Item name="title" label={target?.isCard ? '卡片标题' : '栏目名称'}
          rules={[{required: true, whitespace: true, max: 100}]}>
          <Input maxLength={100} showCount/>
        </Form.Item>
        {target?.isCard && <Form.Item name="content" label="正文" preserve={false}
          rules={[{required: true, whitespace: true, max: 8000}]}>
          <Input.TextArea autoSize={{minRows: 4, maxRows: 10}} maxLength={8000} showCount/>
        </Form.Item>}
        <Form.Item name="sort_order" label="排序" extra="数字越小越靠前" rules={[{required: true, type: 'integer', min: 0, max: 9999}]}>
          <InputNumber min={0} max={9999} precision={0}/>
        </Form.Item>
        <Form.Item name="published" label="在官网发布" valuePropName="checked">
          <Switch aria-label="在官网发布"/>
        </Form.Item>
      </Form>
    </Modal>
  </>
}
