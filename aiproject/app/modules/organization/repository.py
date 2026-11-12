from sqlalchemy import select
from app.modules.student_admin.models import SysUser
from .models import sys_organization as org

class OrganizationRepository:
    def __init__(self, db):
        self.db = db

    def list_organizations(self, keyword, limit):
        stmt = select(org).where(org.c.status == 1)
        if keyword:
            stmt = stmt.where(org.c.org_name.contains(keyword, autoescape=True))
        return [dict(row._mapping) for row in self.db.execute(stmt.order_by(org.c.sort_order, org.c.id).limit(limit))]

    def find_colleagues(self, name):
        stmt = select(SysUser.id, SysUser.real_name, SysUser.department).where(
            SysUser.user_type == "employee", SysUser.status == "normal",
            SysUser.real_name.contains(name, autoescape=True),
        ).limit(50)
        return [dict(row._mapping) for row in self.db.execute(stmt)]

    def get_employee(self, employee_id):
        return self.db.get(SysUser, employee_id)
