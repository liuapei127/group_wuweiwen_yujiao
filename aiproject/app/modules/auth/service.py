"""Authentication, live RBAC and account-management transactions."""
import hashlib
from sqlalchemy.exc import IntegrityError, OperationalError, ProgrammingError
from fastapi import HTTPException
from app.core.config import get_settings
from app.core.exceptions import BusinessError
from app.core.security.credentials import require_auth_config, hash_password, verify_password, issue_token, decode_token, utc_now
from app.core.security.rbac import PERMISSIONS
from .repository import AuthRepository

class AuthService:
    def __init__(self,db):
        self.db=db
        self.repo=AuthRepository(db)

    def login(self,body,remote):
        settings=get_settings();require_auth_config(settings)
        key=hashlib.sha256((body.username.strip().casefold()+'|'+remote).encode()).hexdigest()
        try:
            if self.repo.failed_attempts(key)>=10:raise HTTPException(429,'登录尝试过多，请15分钟后重试')
            row=self.repo.account(username=body.username.strip())
            valid=verify_password(body.password,row.get('password_hash') if row else None)
            if not valid or not row or row['status']!='normal' or row['role_status']!=1 or row['user_type'] not in ('employee','admin'):
                self.repo.add_failure(key);self.db.commit()
                raise HTTPException(401,'账号或密码错误',headers={'WWW-Authenticate':'Bearer'})
            token,sid,expires=issue_token(row['id'],settings)
            self.repo.create_session(sid,row['id'],expires)
            self.repo.audit(row['id'],'login',row['id'])
            profile=self.profile(row)
            self.db.commit()
            return {'access_token':token,'token_type':'bearer','expires_at':expires.isoformat()+'Z','user':profile}
        except (OperationalError,ProgrammingError):
            self.db.rollback();raise HTTPException(503,'身份存储未就绪，请先初始化认证表') from None

    def authenticate(self,token):
        claims=decode_token(token,get_settings())
        uid=int(claims['sub'])
        try:
            session=self.repo.active_session(claims['sid'],uid)
            row=self.repo.account(user_id=uid)
            if not session or not row or row['status']!='normal' or row['role_status']!=1 or row['user_type'] not in ('employee','admin'):
                raise HTTPException(401,'登录已失效，请重新登录',headers={'WWW-Authenticate':'Bearer'})
            from app.core.security.dependencies import EmployeePrincipal
            return EmployeePrincipal(employee_id=uid,permissions=frozenset(self.repo.permissions(row['role_id'])&set(PERMISSIONS)),
                student_ids=frozenset(self.repo.scope(uid)),username=row['username'],role_code=row['role_code'],session_id=claims['sid'])
        except (OperationalError,ProgrammingError):
            self.db.rollback();raise HTTPException(503,'身份存储未就绪') from None

    def profile(self,row):
        return {**{k:row[k] for k in ('id','username','real_name','user_type','role_id','role_code','role_name','department','contact_info','status')},
            'permissions':sorted(self.repo.permissions(row['role_id'])&set(PERMISSIONS)),
            'student_ids':sorted(self.repo.scope(row['id']))}

    def me(self,p):
        return self.profile(self.repo.account(user_id=p.employee_id))

    def logout(self,p):
        self.repo.revoke(p.employee_id,p.session_id);self.repo.audit(p.employee_id,'logout',p.employee_id);self.db.commit()
        return {'logged_out':True}

    def change_password(self,body,p):
        row=self.repo.account(user_id=p.employee_id)
        if not verify_password(body.old_password,row['password_hash']):raise BusinessError(400,'原密码不正确')
        self.repo.update_account(p.employee_id,{'password_hash':hash_password(body.new_password),'update_time':utc_now()})
        self.repo.revoke(p.employee_id);self.repo.audit(p.employee_id,'password_change',p.employee_id);self.db.commit()
        return {'relogin_required':True}

    def _role(self,role_id):
        role=self.repo.role(role_id)
        if not role or role['status']!=1 or role['role_code']=='student':raise BusinessError(422,'请选择启用的员工角色')
        return role

    def _employee(self,user_id):
        row=self.repo.account(user_id=user_id)
        if not row or row['user_type'] not in ('employee','admin'):raise BusinessError(404,'员工不存在')
        return row

    def _keep_admin(self):
        if self.repo.admin_count()<1:raise BusinessError(409,'至少保留一名启用且拥有员工和角色管理权限的管理员')

    def create_user(self,body,p):
        self._role(body.role_id)
        try:
            values=body.model_dump(exclude={'password'})
            values.update(password_hash=hash_password(body.password),user_type='employee',create_time=utc_now(),update_time=utc_now())
            rid=self.repo.create_account(values)
            self.repo.audit(p.employee_id,'user_create',rid,{'username':body.username,'role_id':body.role_id})
            self.db.commit();return {'id':rid}
        except IntegrityError:
            self.db.rollback();raise BusinessError(409,'账号已存在') from None

    def update_user(self,user_id,body,p):
        try:
            self.repo.lock_policy();self._employee(user_id);self._role(body.role_id)
            self.repo.update_account(user_id,{**body.model_dump(),'update_time':utc_now()})
            self._keep_admin()
            if body.status!='normal':self.repo.revoke(user_id)
            self.repo.audit(p.employee_id,'user_update',user_id,body.model_dump())
            self.db.commit();return {'id':user_id}
        except Exception:
            self.db.rollback();raise

    def reset_password(self,user_id,body,p):
        self._employee(user_id)
        self.repo.update_account(user_id,{'password_hash':hash_password(body.new_password),'update_time':utc_now()})
        self.repo.revoke(user_id);self.repo.audit(p.employee_id,'password_reset',user_id);self.db.commit()
        return {'id':user_id,'sessions_revoked':True}

    def set_scope(self,user_id,body,p):
        self._employee(user_id)
        ids=set(body.student_ids)
        if any(type(s) is not int or s<1 for s in ids):raise BusinessError(422,'学生编号必须为正整数')
        valid={s['id'] for s in self.repo.students(ids)}
        if valid!=ids:raise BusinessError(422,'包含不存在或停用的学生')
        try:
            self.repo.replace_scope(user_id,ids);self.repo.audit(p.employee_id,'student_scope_update',user_id,{'student_ids':sorted(ids)})
            self.db.commit();return {'id':user_id,'student_ids':sorted(self.repo.scope(user_id))}
        except Exception:
            self.db.rollback();raise

    def save_role(self,body,p,role_id=None):
        unknown=set(body.permissions)-set(PERMISSIONS)
        if unknown:raise BusinessError(422,'包含未注册的功能权限')
        try:
            self.repo.lock_policy()
            old=self.repo.role(role_id) if role_id else None
            if role_id and not old:raise BusinessError(404,'角色不存在')
            if old and old['role_code']=='student':raise BusinessError(403,'学生基础角色不由员工门户修改')
            values={**body.model_dump(exclude={'permissions'}),'update_time':utc_now()}
            if role_id:
                if body.role_code!=old['role_code']:raise BusinessError(422,'已创建角色的编码不可修改')
                self.repo.update_role(role_id,values)
            else:
                if body.role_code=='student':raise BusinessError(422,'该角色编码已保留')
                role_id=self.repo.create_role({**values,'create_time':utc_now()})
            self.repo.replace_permissions(role_id,body.permissions)
            self._keep_admin()
            self.repo.audit(p.employee_id,'role_save',role_id,{'role_code':body.role_code,'permissions':sorted(set(body.permissions)),'status':body.status})
            self.db.commit();return {'id':role_id}
        except IntegrityError:
            self.db.rollback();raise BusinessError(409,'角色编码已存在') from None
        except Exception:
            self.db.rollback();raise

    def status(self):
        settings=get_settings()
        configured=settings.employee_identity_mode=='trusted_jwt' and len(settings.auth_jwt_secret.get_secret_value())>=32
        return {'mode':settings.employee_identity_mode,'ready':configured and self.repo.ready()}

    def users(self,keyword,page,page_size):
        return self.repo.list_users(keyword,page,page_size)

    def roles(self):
        return self.repo.list_roles()

    def catalog(self):
        from app.core.security.rbac import permission_catalog
        return permission_catalog()

    def students(self):
        return self.repo.students()

    def audits(self,limit):
        return self.repo.audits(limit)
