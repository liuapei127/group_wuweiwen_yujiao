import {useState} from 'react'
import {Button, Card, Space} from 'antd'
import {useMutation, useQuery} from '@tanstack/react-query'
import {api, type Row} from '../lib/api'
import {ActionModal, DetailDrawer, ErrorNotice, PageTitle, Status, type ActionSpec} from '../components/shared'
import {Table} from 'antd'

export function TicketRouting() {
  const [action, setAction] = useState<ActionSpec | null>(null)
  const [history, showHistory] = useState<unknown>()
  const [historyError, setHistoryError] = useState<Error>()
  const records = useQuery({
    queryKey: ['ticket-routing'], queryFn: () => api<Row[]>('/api/v1/enterprise/ticket-routing'),
  })
  async function viewHistory(id: number) {
    try {setHistoryError(undefined); showHistory(await api('/api/v1/enterprise/tickets/' + id + '/history'))}
    catch (error) {setHistoryError(error as Error)}
  }
  const classify = useMutation({
    mutationFn: (row: Row) => api<{category:string}>('/api/v1/reporting/board/complaints/'+row.id+'/classification',
      {method:'POST',timeout:130000}),
    onSuccess: (result,row) => setAction({
      title:'核验 AI 分类建议',path:'/api/v1/enterprise/ticket-routing/'+row.id,method:'PUT',
      fields:[
        {name:'category',label:'建议分类',kind:'select',required:true,initial:row.category==='company'?'company':result.category,
          options:row.category==='company'?[{value:'company',label:'主管处理（保密）'}]:[{value:'learning',label:'学习相关，交班主任'},{value:'company',label:'公司相关，交主管'}]},
        {name:'reason',label:'核验说明',kind:'textarea',required:true},
      ],
      transform:values=>({...values,expected_status:row.status,expected_category:row.category,expected_assignee_id:row.assignee_id}),
    }),
  })
  return <>
    <PageTitle title="投诉分类与分派" description="学习反馈可上报主管；主管受理的内容保持保密，不转回班主任。"/>
    <ErrorNotice error={records.error || historyError || classify.error}/>
    <Card>
      <Table<Row> rowKey="id" dataSource={records.data ?? []} loading={records.isFetching} columns={[
        {title: '编号', dataIndex: 'id'}, {title: '学生编号', dataIndex: 'student_id', width: 130},
        {title: '姓名', dataIndex: 'student_name', width: 120, render: value => value || '—'},
        {title: '内容', dataIndex: 'content'},
        {title: '分类', render: (_, row) => row.category === 'learning' ? '学习相关' : row.category === 'company' ? '公司相关' : '待核对'},
        {title: '负责人编号', dataIndex: 'assignee_id'},
        {title: '状态', render: (_, row) => <Status value={row.status}/>},
        {title: '操作', render: (_, row) => <Space>
          <Button type="link" loading={classify.isPending&&classify.variables?.id===row.id}
            onClick={()=>classify.mutate(row)}>AI 建议分类</Button>
          <Button type="link" onClick={() => setAction({
            title: '修正投诉分派', path: '/api/v1/enterprise/ticket-routing/' + row.id, method: 'PUT',
            fields: [
              {name: 'category', label: '正确分类', kind: 'select', required: true,
                options: row.category==='company'?[{value:'company',label:'主管处理（保密）'}]:[{value: 'learning', label: '学习相关，交该学生班主任'}, {value: 'company', label: '公司相关，交主管'}]},
              {name: 'reason', label: '修正原因', kind: 'textarea', required: true},
            ],
            transform: values => ({...values, expected_status: row.status,
              expected_category: row.category, expected_assignee_id: row.assignee_id}),
          })}>修正分派</Button>
          <Button type="link" onClick={() => void viewHistory(row.id)}>处理历史</Button>
        </Space>},
      ]}/>
    </Card>
    <ActionModal action={action} onClose={() => setAction(null)}/>
    <DetailDrawer title="工单处理历史" data={history} onClose={() => showHistory(undefined)}/>
  </>
}
