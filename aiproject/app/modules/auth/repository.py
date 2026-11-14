"""SQL for shared accounts and ENT-owned RBAC/session tables. No commits."""
import json
from datetime import timedelta
from sqlalchemy import select, insert, update, delete, func, and_, inspect, table, column, BigInteger, String
from .models import accounts, roles, role_permissions, student_scopes, sessions, login_attempts, audit_log
from app.core.security.credentials import utc_now

student_info = table('student_info',column('id',BigInteger),column('user_id',BigInteger),
                     column('class_teacher_id',BigInteger),column('student_no',String),
                     column('school',String),column('major',String),column('abroad_country',String))
PUBLIC_COLUMNS = [accounts.c.id,accounts.c.username,accounts.c.real_name,accounts.c.user_type,
                  accounts.c.role_id,accounts.c.department,accounts.c.contact_info,accounts.c.status,
                  accounts.c.create_time,roles.c.role_code,roles.c.role_name]

class AuthRepository:
    def __init__(self, db):
        self.db = db

    def ready(self):
        return all(inspect(self.db.get_bind()).has_table(n) for n in
                   ('ent_auth_session','ent_auth_role_permission','ent_auth_student_scope','ent_auth_audit'))

    def account(self, user_id=None, username=None):
        stmt=select(accounts,roles.c.role_code,roles.c.role_name,roles.c.status.label('role_status')).select_from(
            accounts.outerjoin(roles,accounts.c.role_id==roles.c.id))
        stmt=stmt.where(accounts.c.id==user_id) if user_id is not None else stmt.where(func.lower(accounts.c.username)==username.lower())
        row=self.db.execute(stmt).mappings().first()
        return dict(row) if row else None

    def lock_account_id(self, user_id):
        return self.db.scalar(select(accounts.c.id).where(accounts.c.id == user_id).with_for_update())

    def permissions(self, role_id):
        return set(self.db.execute(select(role_permissions.c.permission).where(role_permissions.c.role_id==role_id)).scalars()) if role_id else set()

    def scope(self, user_id):
        explicit=set(self.db.execute(select(student_scopes.c.student_id).where(student_scopes.c.user_id==user_id)).scalars())
        # Existing class-teacher assignment is authoritative; no client-supplied scope.
        assigned=set(self.db.execute(select(student_info.c.user_id).where(student_info.c.class_teacher_id==user_id)).scalars())
        ids=explicit|assigned
        if not ids:return set()
        return set(self.db.execute(select(accounts.c.id).where(accounts.c.id.in_(ids),accounts.c.user_type=='student',accounts.c.status=='normal')).scalars())

    def explicit_scope(self,user_id):
        return list(self.db.execute(select(student_scopes.c.student_id).where(student_scopes.c.user_id==user_id)).scalars())

    def active_session(self,sid,user_id):
        return self.db.execute(select(sessions).where(sessions.c.id==sid,sessions.c.user_id==user_id,
            sessions.c.revoked_at.is_(None),sessions.c.expires_at>utc_now())).mappings().first()

    def create_session(self,sid,user_id,expires):
        self.db.execute(insert(sessions).values(id=sid,user_id=user_id,expires_at=expires,create_time=utc_now()))

    def revoke(self,user_id,sid=None):
        stmt=update(sessions).where(sessions.c.user_id==user_id,sessions.c.revoked_at.is_(None))
        if sid:stmt=stmt.where(sessions.c.id==sid)
        self.db.execute(stmt.values(revoked_at=utc_now()))

    def failed_attempts(self,key):
        return self.db.execute(select(func.count()).select_from(login_attempts).where(
            login_attempts.c.attempt_key==key,login_attempts.c.create_time>utc_now()-timedelta(minutes=15))).scalar_one()

    def add_failure(self,key):
        self.db.execute(insert(login_attempts).values(attempt_key=key,create_time=utc_now()))

    def audit(self,actor,action,target=None,details=None):
        self.db.execute(insert(audit_log).values(actor_id=actor,action=action,target=str(target) if target is not None else None,
            details=json.dumps(details or {},ensure_ascii=False,default=str),create_time=utc_now()))

    def list_users(self,keyword,page,page_size):
        where=[accounts.c.user_type.in_(['employee','admin'])]
        if keyword:
            where.append(accounts.c.real_name.contains(keyword,autoescape=True)|accounts.c.username.contains(keyword,autoescape=True))
        total=self.db.execute(select(func.count()).select_from(accounts).where(*where)).scalar_one()
        stmt=select(*PUBLIC_COLUMNS).select_from(accounts.outerjoin(roles,accounts.c.role_id==roles.c.id)).where(*where)
        rows=[dict(r) for r in self.db.execute(stmt.order_by(accounts.c.id.desc()).offset((page-1)*page_size).limit(page_size)).mappings()]
        for row in rows:row['student_ids']=self.explicit_scope(row['id'])
        choices=[{k:r[k] for k in ('id','role_code','role_name','status')} for r in self.list_roles()]
        return {'items':rows,'total':total,'page':page,'page_size':page_size,'roles':choices}

    def list_roles(self):
        rows=[dict(r) for r in self.db.execute(select(roles).order_by(roles.c.id)).mappings()]
        for r in rows:r['permissions']=sorted(self.permissions(r['id']))
        return rows

    def role(self,rid):
        row=self.db.execute(select(roles).where(roles.c.id==rid)).mappings().first()
        return dict(row) if row else None

    def create_account(self,values):
        return self.db.execute(insert(accounts).values(**values)).lastrowid

    def update_account(self,user_id,values):
        self.db.execute(update(accounts).where(accounts.c.id==user_id).values(**values))

    def create_role(self,values):
        return self.db.execute(insert(roles).values(**values)).inserted_primary_key[0]

    def update_role(self,role_id,values):
        self.db.execute(update(roles).where(roles.c.id==role_id).values(**values))

    def replace_permissions(self,role_id,permissions):
        self.db.execute(delete(role_permissions).where(role_permissions.c.role_id==role_id))
        if permissions:self.db.execute(insert(role_permissions),[{'role_id':role_id,'permission':p} for p in sorted(set(permissions))])

    def replace_scope(self,user_id,ids):
        self.db.execute(delete(student_scopes).where(student_scopes.c.user_id==user_id))
        if ids:self.db.execute(insert(student_scopes),[{'user_id':user_id,'student_id':s} for s in sorted(set(ids))])

    def students(self,ids=None):
        stmt=select(accounts.c.id,accounts.c.real_name,student_info.c.student_no,student_info.c.school,student_info.c.class_teacher_id).select_from(
            accounts.outerjoin(student_info,student_info.c.user_id==accounts.c.id)).where(accounts.c.user_type=='student',accounts.c.status=='normal')
        if ids is not None:
            if not ids:return []
            stmt=stmt.where(accounts.c.id.in_(ids))
        return [dict(r) for r in self.db.execute(stmt.order_by(accounts.c.id).limit(1000)).mappings()]

    def lock_policy(self):
        self.db.execute(select(roles.c.id).order_by(roles.c.id).with_for_update()).all()

    def admin_count(self):
        a=role_permissions.alias('manage_users');b=role_permissions.alias('manage_roles')
        join=accounts.join(roles,roles.c.id==accounts.c.role_id).join(a,and_(a.c.role_id==roles.c.id,a.c.permission=='users:manage')).join(b,and_(b.c.role_id==roles.c.id,b.c.permission=='roles:manage'))
        return self.db.execute(select(func.count(func.distinct(accounts.c.id))).select_from(join).where(
            accounts.c.status=='normal',accounts.c.user_type.in_(['employee','admin']),roles.c.status==1)).scalar_one()

    def audits(self,limit):
        rows=[dict(r) for r in self.db.execute(select(audit_log).order_by(audit_log.c.id.desc()).limit(limit)).mappings()]
        for r in rows:r['details']=json.loads(r['details'])
        return rows


    def eligible_employee_ids(self, role_code: str, permissions: tuple[str, ...], limit: int = 2) -> list[int]:
        stmt = select(accounts.c.id).join(roles, accounts.c.role_id == roles.c.id).where(
            accounts.c.user_type == "employee", accounts.c.status == "normal",
            roles.c.role_code == role_code, roles.c.status == 1,
        )
        for permission in permissions:
            stmt = stmt.where(select(role_permissions.c.role_id).where(
                role_permissions.c.role_id == roles.c.id,
                role_permissions.c.permission == permission,
            ).exists())
        return list(self.db.scalars(stmt.order_by(accounts.c.id).limit(limit)))
