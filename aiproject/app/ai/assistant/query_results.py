"""Deterministic views of already-authorized query data; no model or database access."""
from datetime import datetime, timedelta, timezone

LABELS = {
    'title':'标题', 'description':'说明', 'content':'内容', 'status':'状态', 'priority':'优先级',
    'todo_type':'待办类型', 'due_time':'到期时间', 'completed_time':'完成时间',
    'related_type':'关联事项', 'related_id':'关联编号', 'create_time':'创建时间', 'update_time':'更新时间',
    'customer_name':'客户姓名', 'intended_country':'意向国家', 'intended_major':'意向专业',
    'age':'年龄', 'education_level':'学历', 'background_info':'背景信息', 'remark':'备注',
    'last_contact_time':'最近联系时间', 'student_id':'学生编号', 'student_name':'学生姓名',
    'leave_type':'请假类型', 'start_time':'开始时间', 'end_time':'结束时间', 'reason':'原因',
    'approval_comment':'审批意见', 'approval_time':'审批时间', 'solution':'处理说明',
    'ticket_type':'工单类型', 'category':'分类', 'real_name':'姓名', 'department':'部门',
    'org_name':'组织名称', 'contact_info':'联系方式', 'report_date':'报告日期',
    'key_progress':'关键进展', 'risks':'风险', 'next_plan':'下一步计划', 'course_name':'课程',
    'score':'成绩', 'semester':'学期', 'version':'版本', 'correction_reason':'更正原因',
    'score_id':'成绩编号', 'old_score':'原成绩', 'new_score':'更正后成绩',
    'notification_type':'通知类型', 'follow_type':'跟进方式', 'total':'总数', 'count':'数量',
    'operation':'操作', 'change_reason':'更正原因', 'before_data':'更正前', 'after_data':'更正后',
    'study_stage':'学习阶段', 'credit':'学分',
}
VALUES = {
    'status': {'pending':'待处理', 'in_progress':'进行中', 'done':'已完成', 'cancelled':'已取消',
               'processing':'处理中', 'resolved':'已解决', 'closed':'已关闭', 'approved':'已批准',
               'rejected':'已拒绝', 'submitted':'已提交', 'draft':'草稿', 'sent':'已发送',
               'failed':'发送失败', 'new':'新线索', 'contacting':'联系中', 'qualified':'已确认意向',
               'signed':'已签约', 'lost':'已流失'},
    'priority': {'low':'低', 'medium':'中', 'high':'高', 'urgent':'紧急'},
    'todo_type': {'leave_approval':'请假审批', 'complaint_follow':'投诉跟进', 'report_remind':'报表提醒', 'custom':'自定义'},
    'related_type': {'student_feedback_ticket':'学生投诉与建议工单', 'student_admin_service':'学生请假', 'student_psych_alert':'心理预警'},
    'ticket_type': {'complaint':'投诉', 'suggestion':'建议', 'consultation':'咨询'},
    'category': {'learning':'学习类', 'company':'公司服务类'},
    'leave_type': {'sick':'病假', 'personal':'事假', 'emergency':'紧急请假'},
    'follow_type': {'phone':'电话', 'wechat':'微信', 'meeting':'面谈', 'email':'邮件', 'other':'其他'},
    'operation': {'create':'新增', 'correct':'更正'},
    'study_stage': {'foundation':'预科', 'language':'语言培训', 'overseas':'海外院校', 'unspecified':'未指定'},
}
TODO = ('title','todo_type','status','priority','due_time','description','related_type','related_id','completed_time')
LEAVE = ('student_name','student_id','leave_type','start_time','end_time','reason','status','approval_comment','approval_time')
TICKET = ('title','student_name','student_id','ticket_type','category','content','status','solution','create_time','update_time')
DAILY = ('report_date','content','key_progress','risks','next_plan','status')
FOLLOW = ('follow_type','content','next_plan','create_time')
CONFIG = {
    'todos':('待办',TODO), 'leaves':('请假单',LEAVE), 'leave_candidates':('请假单',LEAVE),
    'tickets':('工单',TICKET), 'ticket_detail':('工单',TICKET), 'daily_list':('日报',DAILY),
    'guides':('指南',('title','category','content','update_time')),
    'colleagues':('同事',('real_name','department','org_name')),
    'colleague_contact':('同事',('real_name','department','contact_info')),
    'score_history':('成绩更正记录',('score_id','version','operation','change_reason','before_data','after_data','create_time')),
    'notifications':('通知',('title','content','notification_type','status','create_time')),
}
NATURAL_QUERIES = {
    'leads_by_status':('客户',('customer_name','status','intended_country','count','total')),
    'lead_detail_by_name':('客户',('customer_name','status','intended_country','intended_major','remark')),
    'lead_follow_ups_by_name':('跟进记录',FOLLOW), 'pending_leaves':('请假单',LEAVE), 'daily_reports_recent':('日报',DAILY),
}


def _value(key, value):
    if value is None or value == '':
        return '未提供'
    if isinstance(value, bool):
        return '是' if value else '否'
    if isinstance(value, list):
        return '；'.join(_value(key, item) for item in value) or '无'
    if isinstance(value, dict):
        return '；'.join(f'{LABELS.get(str(k), str(k))}：{_value(key, v)}' for k, v in value.items()
                        if not isinstance(v, (dict, list)) and (key not in ('before_data','after_data') or k in LABELS)) or '无可展示内容'
    text = str(value)
    if key.endswith(('_time', '_at')):
        try:
            date = datetime.fromisoformat(text.replace('Z', '+00:00'))
            if date.tzinfo:
                date = date.astimezone(timezone(timedelta(hours=8)))
            return date.strftime('%Y-%m-%d %H:%M:%S')
        except ValueError:
            pass
    return VALUES.get(key, {}).get(text, text)


def _records(data, name, fields):
    rows, extra = data, ''
    if isinstance(data, dict):
        rows = data.get('items', data.get('rows', [data]))
        if isinstance(data.get('total'), int):
            extra = f"（匹配总数 {data['total']} 条）"
        if data.get('has_more'):
            extra += '，后续还有记录'
    if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
        return f'{name}查询返回的格式有误，请稍后重试。'
    if not rows:
        return f'本次查询没有找到符合条件的{name}。'
    lines = [f'本次返回 {len(rows)} 条{name}{extra}：']
    for index, row in enumerate(rows[:30], 1):
        lines.append(f'\n{index}. {name}' + (f"编号：{row['id']}" if row.get('id') is not None else ''))
        for key in fields:
            if key in row:
                lines.append(f'{LABELS[key]}：{_value(key, row[key])}')
    if len(rows) > 30:
        lines.append('\n当前展示前 30 条，请缩小查询范围或在对应业务页面查看其余记录。')
    return '\n'.join(lines)


def query_result(intent, data):
    if intent in CONFIG:
        reply = _records(data, *CONFIG[intent])
    elif intent == 'lead_detail':
        if not isinstance(data, dict) or not isinstance(data.get('lead'), dict):
            return '客户详情查询返回的格式有误，请稍后重试。'
        fields = ('customer_name','status','intended_country','intended_major','age','education_level','background_info','remark','last_contact_time')
        reply = _records(data['lead'], '客户', fields)
        if isinstance(data.get('follow_ups'), list):
            reply += '\n\n' + _records(data['follow_ups'], '跟进记录', FOLLOW)
    elif intent == 'nl_query':
        if not isinstance(data, dict) or data.get('intent') not in NATURAL_QUERIES:
            return '查询返回的格式有误，请稍后重试。'
        if data['intent'] == 'lead_detail_by_name' and isinstance(data.get('result'), dict) and 'lead' in data['result']:
            return query_result('lead_detail', data['result'])
        reply = _records(data.get('result'), *NATURAL_QUERIES[data['intent']])
    else:
        return None
    if len(reply) > 12000:
        return reply[:12000] + '\n内容较长，已截取前段；请缩小查询范围或到对应业务页面查看完整内容。'
    return reply
