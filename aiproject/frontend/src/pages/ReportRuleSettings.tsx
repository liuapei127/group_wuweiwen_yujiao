import {App, Button, Card, Form, InputNumber, Select, Typography} from 'antd'
import {useMutation, useQuery, useQueryClient} from '@tanstack/react-query'
import {useAuth} from '../auth'
import {api} from '../lib/api'
import {ErrorNotice} from '../components/shared'

type Settings = Record<string,number|string|null>
type Rules = {version:number;settings:Settings}
const fields = [
  ['high_value_match_score','高价值候选客户最低研判匹配度',100],
  ['lead_inactive_days','未联系客户预警天数',365],
  ['complaint_overdue_days','投诉未解决预警天数',365],
  ['complaint_escalate_days','投诉升级通知经理的天数',365],
  ['reminder_repeat_days','未解决事项重复提醒间隔（天）',90],
  ['psych_negative_days','自评连续低落或高压力的提醒天数',30],
  ['project_complaint_weight','项目评分中未解决投诉的权重',1],
  ['project_application_weight','项目评分中过期申请的权重',1],
  ['project_deadline_weight','项目评分中过期考务的权重',1],
] as const

export function ReportRuleSettings() {
  const {user}=useAuth()
  const {message}=App.useApp()
  const cache=useQueryClient()
  const key=[user?.id,'report-rules']
  const current=useQuery({queryKey:key,queryFn:()=>api<Rules>('/api/v1/reporting/rules')})
  const save=useMutation({mutationFn:(values:Settings)=>api<Rules>('/api/v1/reporting/rules',{
    method:'PUT',body:{expected_version:current.data?.version,settings:values}}),
    onSuccess:row=>{cache.setQueryData(key,row);void message.success('报表规则已保存')}})
  return <Card title="报表分析与预警规则" loading={current.isPending}>
    <ErrorNotice error={current.error||save.error}/>
    <Typography.Paragraph>留空表示该项尚未启用。高价值候选按已有研判匹配度筛选，心理自评提示由班主任人工核验。项目评分的三个权重须同时填写，合计为 1。</Typography.Paragraph>
    {current.data&&<Form key={current.data.version} layout="vertical" initialValues={current.data.settings}
      onFinish={values=>save.mutate(values)} style={{maxWidth:620}}>
      {fields.map(([name,label,max])=><Form.Item name={name} label={label} key={name}>
        <InputNumber min={name.includes('weight')||name==='high_value_match_score'?0:name==='psych_negative_days'?2:1}
          max={max} precision={name.includes('weight')?2:0} style={{width:'100%'}} placeholder="尚未设置"/>
      </Form.Item>)}
      <Form.Item name="psych_alert_level" label="自评触发后的待核验预警等级">
        <Select allowClear options={[{value:'low',label:'低风险提示'},{value:'medium',label:'中风险提示'},{value:'high',label:'高风险提示'}]}
          placeholder="与自评提醒天数一同设置"/>
      </Form.Item>
      <Button htmlType="submit" type="primary" loading={save.isPending}>保存规则</Button>
    </Form>}
  </Card>
}
