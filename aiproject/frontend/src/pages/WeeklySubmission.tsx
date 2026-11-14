import {useState} from 'react'
import {App,Button,Card,Form,Input,Space} from 'antd'
import {useMutation,useQuery,useQueryClient} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {api,query} from '../lib/api'
import {ErrorNotice} from '../components/shared'
import {today} from './reportDates'

type Fields={content:string;key_progress?:string;risks?:string;next_plan?:string}
const endpoint='/api/v1/employee-reports/weekly'

export function WeeklySubmission(){
  const {user,can}=useAuth()
  const {message}=App.useApp()
  const [anchor,setAnchor]=useState(today)
  const cache=useQueryClient()
  const key=[user?.id,'weekly-submission',anchor]
  const data=useQuery({queryKey:key,enabled:!!anchor,queryFn:()=>api<Fields|null>(endpoint+query({anchor}))})
  const save=useMutation({mutationFn:(values:Fields)=>api(endpoint,{method:'PUT',body:{anchor,...values}}),
    onSuccess:()=>{void cache.invalidateQueries({queryKey:key});void cache.invalidateQueries({queryKey:[user?.id,'/api/v1/reporting/board/employees']});void message.success('周报已保存')}})
  return <Card title="我的员工周报" style={{marginTop:16}}>
    <Space orientation="vertical" style={{width:'100%'}}>
      <Input aria-label="我的周报日期" type="date" value={anchor} onChange={e=>setAnchor(e.target.value)} style={{width:180}}/>
      <ErrorNotice error={data.error||save.error}/>
      {anchor && data.isSuccess && <Form<Fields> key={anchor+String(!!data.data)} layout="vertical" initialValues={data.data||{}}
        disabled={save.isPending||!can('reports:write')} onFinish={values=>save.mutate(values)}>
        {([['content','工作总结'],['key_progress','关键进展'],['risks','风险事项'],['next_plan','下一步计划']] as const).map(([name,label])=>
          <Form.Item key={name} name={name} label={label} rules={name==='content'?[{required:true,whitespace:true}]:[]}>
            <Input.TextArea rows={name==='content'?4:2} maxLength={name==='content'?8000:4000}/>
          </Form.Item>)}
        {can('reports:write')&&<Button type="primary" htmlType="submit">保存周报</Button>}
      </Form>}
    </Space>
  </Card>
}
