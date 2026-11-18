import {useState} from 'react'
import {Button,Card,Space,Table,Tag,Typography} from 'antd'
import {useQuery} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {api,query} from '../lib/api'
import {ErrorNotice} from './shared'

type Reservation={
  id:number;event_id:number;event_name:string;location:string|null;event_status:string
  start_time:string;end_time:string|null;status:string;reserved_at:string
  cancelled_at:string|null;attended_at:string|null
}
const pageSize=20
const statuses:Record<string,string>={registered:'已预约',cancelled:'已取消',attended:'已签到',no_show:'未到场'}
const eventStatuses:Record<string,string>={upcoming:'未开始',ongoing:'进行中',ended:'已结束',cancelled:'活动已取消'}
// Event dates are stored and returned as Beijing local time, unlike intake UTC timestamps.
const eventTime=(value:string|null)=>value?value.slice(0,16).replace('T',' '):'—'

export function VisitorReservations({visitorId}:{visitorId:number}){
  const {user}=useAuth()
  const [before,setBefore]=useState<number>()
  const result=useQuery({
    queryKey:[user?.id,'visitor-intake',visitorId,'reservations',before],
    queryFn:()=>api<Reservation[]>('/api/v1/consultant/visitor-intake/'+visitorId+'/reservations'+query({before_id:before,limit:pageSize})),
    refetchInterval:30_000,
  })
  return <Card title="活动预约与签到" extra={<Button size="small" loading={result.isFetching} onClick={()=>void result.refetch()}>刷新预约</Button>}>
    <Typography.Paragraph type="secondary">仅显示你当前认领游客的记录，每 30 秒更新。所有时间均为北京时间。</Typography.Paragraph>
    <ErrorNotice error={result.error}/>
    <Table<Reservation> rowKey="id" size="small" loading={result.isFetching} pagination={false}
      scroll={{x:900}} dataSource={result.error?[]:result.data||[]} locale={{emptyText:'该游客暂无活动预约'}} columns={[
        {title:'活动',dataIndex:'event_name',width:200,render:(name,row)=><Space orientation="vertical" size={2}>
          <Typography.Text strong>{name}</Typography.Text><Typography.Text type="secondary">{eventStatuses[row.event_status]||row.event_status}</Typography.Text>
        </Space>},
        {title:'开始时间',dataIndex:'start_time',render:eventTime,width:150},
        {title:'地点',dataIndex:'location',render:value=>value||'—',width:150},
        {title:'预约状态',dataIndex:'status',width:100,render:value=><Tag color={value==='attended'?'success':value==='registered'?'blue':'default'}>{statuses[value]||value}</Tag>},
        {title:'预约时间',dataIndex:'reserved_at',render:eventTime,width:150},
        {title:'签到时间',dataIndex:'attended_at',render:eventTime,width:150},
        {title:'取消时间',dataIndex:'cancelled_at',render:eventTime,width:150},
      ]}/>
    <Space style={{marginTop:12}}>
      <Button disabled={before===undefined||result.isFetching} onClick={()=>setBefore(undefined)}>返回最新预约</Button>
      <Button disabled={result.isError||result.data?.length!==pageSize||result.isFetching}
        onClick={()=>setBefore(result.data?.at(-1)?.id)}>查看更多预约</Button>
    </Space>
  </Card>
}
