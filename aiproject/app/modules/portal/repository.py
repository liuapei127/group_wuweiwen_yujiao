from datetime import date
from sqlalchemy import select,func,text
from app.modules.consultant.models import CrmLead
from app.modules.employee_report.models import EmployeeDailyReport
from app.modules.student_admin.models import StudentAdminService
from app.modules.feedback.models import student_feedback_ticket as tickets
from app.modules.todo.models import todo_item as todos, notification_log as notices

class PortalRepository:
    def __init__(self,db):self.db=db

    def counters(self,p):
        result={}
        definitions=[
            ('crm:read','customers',CrmLead,[CrmLead.owner_employee_id==p.employee_id]),
            ('reports:read','reports_today',EmployeeDailyReport,[EmployeeDailyReport.employee_id==p.employee_id,EmployeeDailyReport.report_date==date.today()]),
            ('leaves:read','leaves_pending',StudentAdminService,[StudentAdminService.approver_id==p.employee_id,StudentAdminService.service_type=='leave',StudentAdminService.status=='pending']),
            ('todos:read','todos_open',todos,[todos.c.assignee_id==p.employee_id,todos.c.status.in_(['pending','in_progress'])]),
            ('tickets:read','tickets_open',tickets,[tickets.c.assignee_id==p.employee_id,tickets.c.status.in_(['pending','processing'])]),
            ('notifications:read','notifications',notices,[notices.c.user_id==p.employee_id,notices.c.channel=='system']),
        ]
        for permission,key,model,conditions in definitions:
            if permission in p.permissions:
                result[key]=self.db.execute(select(func.count()).select_from(model).where(*conditions)).scalar_one()
        if 'scores:read' in p.permissions:result['authorized_students']=len(p.student_ids)
        return result

    def database_ready(self):
        return self.db.execute(text('SELECT 1')).scalar_one()==1
