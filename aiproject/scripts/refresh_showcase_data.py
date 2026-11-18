"""Replace local business fixtures with coherent, synthetic presentation records.

Requires a verified full mysqldump backup. Defaults to transaction rollback;
--apply commits only after all foreign-key, identity and chronology checks pass.
Existing staff credentials, permission grants, schema and knowledge config remain.
No outbound messages or external AI/memory writes are performed by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import secrets
from datetime import datetime, time, timedelta
from pathlib import Path

from sqlalchemy import MetaData, delete, func, select, text, update

from app.core.security.credentials import hash_password, utc_now
from app.modules.profile.customer_import import EDUCATION_LABELS, PROJECT_LABELS
from app.modules.profile.portrait import RULE_VERSION, portrait_findings, screening_document
from app.modules.profile.schemas import ScreeningInput
from app.modules.profile.screening import screen_profile
from scripts.seed_full_system_qa import _engine

ROOT = Path(__file__).resolve().parents[1]
KEEP = {
    'sys_user', 'sys_role', 'ent_auth_role_permission', 'ent_auth_session',
    'auth_refresh_token', 'auth_user_session_kid', 'auth_service_client',
    'auth_service_client_audience', 'auth_service_session', 'auth_service_session_kid',
    'intent_config', 'knowledge_base', 'onboarding_guide', 'overseas_life_knowledge',
    'profile_rule', 'report_analysis_rules', 'report_schedule', 'report_schedule_options',
    'website_section', 'website_section_card',
}
STAFF_NAMES = (
    '郑志成', '梁雅文', '徐子恒', '吴佳慧', '宋文博', '何嘉敏',
    '周景明', '林若溪', '陈思齐', '刘婉宁', '赵启航', '许知远',
    '黄舒雅', '王清妍', '谢承泽', '苏芷晴', '陆安然', '沈书言',
)
FEATURED_NAMES = ('陈思远', '林予安', '周沐晴', '赵奕辰', '许清禾', '沈嘉宁')
SURNAMES = tuple('陈林李王张刘黄周吴徐孙胡朱高何郭马罗梁谢宋许郑苏沈陆叶唐顾程')
GIVEN = ('梓涵','沐阳','书瑶','子墨','嘉言','雨桐','奕宁','思睿','若琳','景行','语嫣','泽宇',
         '可欣','知夏','以恒','明轩','星妍','芷萱','昱辰','安琪','清越','浩然','予曦','亦舟',
         '锦程','诗涵','乐言','心怡','承宇','一诺','宇航','梦琪','云舒','予宁','瑾瑜','晨曦')
LOCATIONS = ('广东广州','广东深圳','浙江杭州','江苏苏州','四川成都','湖北武汉','福建厦门','湖南长沙')
CHANNELS = ('官网咨询','朋友推荐','教育展咨询','线上讲座','老生转介绍','校园宣讲')


class Showcase:
    def __init__(self, conn, metadata, now):
        self.c, self.m, self.now = conn, metadata, now
        self.day = now.date()
        self.rng = random.Random(20261118)
        self.names = set(STAFF_NAMES)
        self.phones = set(conn.scalars(text('SELECT username FROM sys_user')))
        self.password = secrets.token_urlsafe(12)
        self.password_hash = hash_password(self.password)
        self.accounts = []
        self.people = []
        self.leads = []
        self.students = []
        self.classes = []
        self.events = []

    def table(self, name):
        return self.m.tables[name]

    def add(self, table, **row):
        result = self.c.execute(self.table(table).insert().values(**row))
        return int(result.lastrowid or 0)

    def at(self, day, hour=2, minute=0):
        return min(datetime.combine(day, time(hour, minute)), self.now)

    def name(self, index):
        if index < len(FEATURED_NAMES):
            candidate = FEATURED_NAMES[index]
        else:
            while (candidate := self.rng.choice(SURNAMES) + self.rng.choice(GIVEN)) in self.names:
                pass
        self.names.add(candidate)
        return candidate

    def mobile(self):
        while (value := self.rng.choice(('138','139','136','158','186','188')) + f'{self.rng.randrange(10**8):08d}') in self.phones:
            pass
        self.phones.add(value)
        return value

    def clear_business(self):
        # Keep FK checks active. Child-first deletion is transactional, unlike TRUNCATE.
        for table in reversed(self.m.sorted_tables):
            if table.name not in KEEP:
                self.c.execute(delete(table))
        student_ids = list(self.c.scalars(text("SELECT id FROM sys_user WHERE user_type='student'")))
        if student_ids:
            sessions = self.table('ent_auth_session')
            session_ids = select(sessions.c.id).where(sessions.c.user_id.in_(student_ids))
            self.c.execute(delete(self.table('auth_refresh_token')).where(self.table('auth_refresh_token').c.user_id.in_(student_ids)))
            self.c.execute(delete(self.table('auth_user_session_kid')).where(self.table('auth_user_session_kid').c.session_id.in_(session_ids)))
            self.c.execute(delete(sessions).where(sessions.c.user_id.in_(student_ids)))
            self.c.execute(delete(self.table('sys_user')).where(self.table('sys_user').c.id.in_(student_ids)))

    def staff_and_organizations(self):
        self.staff = [dict(r) for r in self.c.execute(text(
            "SELECT u.id,u.username,u.real_name,u.status,r.role_code FROM sys_user u "
            "JOIN sys_role r ON r.id=u.role_id WHERE u.user_type<>'student' ORDER BY u.id FOR UPDATE"
        )).mappings()]
        for i, staff in enumerate(self.staff):
            role = staff['role_code']
            department = '教学服务部' if role == 'team_leader' else '综合管理部' if role == 'admin' else '升学咨询部'
            username = staff['username'] if re.fullmatch(r'1\d{10}', staff['username']) else f'19900009{i+1:03d}'
            staff.update(real_name=STAFF_NAMES[i], department=department, username=username)
            self.c.execute(update(self.table('sys_user')).where(self.table('sys_user').c.id == staff['id']).values(
                real_name=staff['real_name'], username=username, department=department,
                contact_info=username, avatar_url=None,
            ))
        active = [s for s in self.staff if s['status'] == 'normal']
        self.admin = next(s for s in active if s['username'] == '19900001101')
        self.advisors = sorted([s for s in active if s['role_code'] == 'employee'], key=lambda s:s['username'] != '19900001102')
        self.teachers = sorted([s for s in active if s['role_code'] == 'team_leader'], key=lambda s:s['username'] != '19900001104')
        self.managers = sorted([s for s in active if s['role_code'] == 'manager'], key=lambda s:s['username'] != '19900001103')
        assert self.advisors and self.teachers and self.managers
        self.c.execute(text('SET @base_org_actor_user_id = :actor'), {'actor': self.admin['id']})
        root = self.add('sys_organization',org_name='粤教升学服务中心',parent_id=None,org_level=1,
                        manager_id=self.admin['id'],sort_order=0,status=1,create_time=self.now,update_time=self.now)
        departments = {}
        for index, name in enumerate(('综合管理部','升学咨询部','教学服务部')):
            manager = self.managers[0]['id'] if name == '升学咨询部' else self.teachers[0]['id'] if name == '教学服务部' else self.admin['id']
            departments[name] = self.add('sys_organization',org_name=name,parent_id=root,org_level=2,
                manager_id=manager,sort_order=index,status=1,create_time=self.now,update_time=self.now)
        for staff in active:
            member = self.add('sys_org_member',user_id=staff['id'],org_id=departments[staff['department']],
                effective_from=self.now-timedelta(days=365),effective_to=None,status='active',
                create_time=self.now,update_time=self.now)
            self.add('sys_user_primary_org',user_id=staff['id'],member_id=member,update_time=self.now)
        self.c.execute(text('SET @base_org_actor_user_id = NULL'))

    def teaching(self):
        catalog = (
            ('de_vocational','德国双元制升学与职业发展','Germany','语言培训及升学规划','12—18个月'),
            ('sg_senior','新加坡高中及同等学历升学','Singapore','国际升学规划','6—12个月'),
            ('sg_top_up','新加坡专升本升学','Singapore','学历提升规划','12个月'),
        )
        self.projects = {}
        for i,(code,name,country,category,duration) in enumerate(catalog):
            project = self.add('course_project',project_name=name,category=category,
                description='提供语言学习规划、材料整理、院校申请辅导及行前准备，具体院校录取条件以申请时公布信息为准。',
                target_audience='有明确海外学习目标、愿意持续提升语言能力的学生',price=None,duration=duration,
                tags=['升学规划','语言学习',country],status=1,create_time=self.now,update_time=self.now)
            self.add('teaching_project',project_id=project,teacher_id=self.teachers[i%len(self.teachers)]['id'],abroad_country=country)
            self.projects[code] = project
        courses = (
            ('德语综合能力','language'),('德语口语与听力','language'),('数学与逻辑基础','preparatory'),
            ('学术英语综合','language'),('英语表达与沟通','language'),('学术阅读与写作','overseas'),
        )
        self.courses = {name:self.add('teaching_course',name=name,study_stage=stage,institution='粤教升学服务中心',enabled=True) for name,stage in courses}
        specs = (
            ('de_vocational','2026秋季德语B1强化班',0),
            ('de_vocational','2026秋季德语A2进阶班',1),
            ('sg_senior','2026秋季新加坡升学一班',2),
            ('sg_senior','2026秋季新加坡升学二班',3),
            ('sg_top_up','2026秋季新加坡专升本一班',0),
            ('sg_top_up','2026秋季新加坡专升本二班',1),
        )
        for code,name,teacher_index in specs:
            teacher = self.teachers[teacher_index%len(self.teachers)]
            course_names = ('德语综合能力','德语口语与听力','数学与逻辑基础') if code == 'de_vocational' else ('学术英语综合','英语表达与沟通','学术阅读与写作')
            class_id = self.add('project_class',project_id=self.projects[code],teacher_id=teacher['id'],name=name,enabled=True)
            for course_name in course_names:
                self.add('class_course',class_id=class_id,course_id=self.courses[course_name])
            self.classes.append({'id':class_id,'name':name,'project':code,'teacher':teacher,'courses':course_names})

    def operating_guides(self):
        # Replace only old interface-verification placeholders with software help,
        # not invented employment rules or company policy.
        guides=(
            ('账号与访问权限','员工使用管理员分配的账号登录工作台。页面菜单按角色权限显示；管理员可在员工管理维护账号，在角色权限中核对授权。'),
            ('客户跟进操作','在资源池认领待跟进访客后，核对本人负责的客户资料。客户详情可维护通用画像、查看资料文件、记录跟进并发起研判。'),
            ('请假审批操作','班主任在请假审批中核对学生、起止时间和申请事由，填写审批意见后提交处理结果。学生可在本人账号查看申请进度。'),
            ('个人资料核对与文件查看','在客户详情核对资料所属人员，点击文件名查看资料内容。出现姓名或手机号冲突时先核对归属，再决定是否导入。'),
        )
        table=self.table('onboarding_guide')
        rows=list(self.c.execute(select(table.c.id).where(table.c.title.like('ENT_LOCAL_VERIFY%')).order_by(table.c.id)))
        for row,(title,body) in zip(rows,guides):
            self.c.execute(update(table).where(table.c.id==row.id).values(title=title,content=body,category='系统操作',embedding_vector=None,update_time=self.now))

    def person(self, index, project=None):
        project = project or self.rng.choice(('de_vocational','sg_senior','sg_top_up','sg_masters','sg_hospitality'))
        if project == 'de_vocational':
            education,age,major = self.rng.choice(('senior_secondary','college')),self.rng.randint(19,27),self.rng.choice(('机电一体化','酒店管理','汽车工程'))
        elif project == 'sg_senior':
            education,age,major = 'senior_secondary',self.rng.randint(17,19),self.rng.choice(('计算机科学','商业管理','数字媒体'))
        elif project == 'sg_top_up':
            education,age,major = 'college',self.rng.randint(21,25),self.rng.choice(('国际商务','信息技术','会计与金融'))
        elif project == 'sg_masters':
            education,age,major = 'bachelor',self.rng.randint(23,29),self.rng.choice(('商业分析','教育管理','国际金融'))
        else:
            education,age,major = 'vocational_secondary',self.rng.randint(18,22),'酒店管理'
        name,phone = self.name(index),self.mobile()
        de = project == 'de_vocational'
        language = self.rng.choice(('德语A2，持续准备B1考试','德语B1，已通过校内口语测评','德语零基础，已制定分阶段学习计划')) if de else self.rng.choice(('雅思5.5，口语需加强','英语四级，日常交流基本流畅','高中英语基础，正在准备入学英语测评'))
        traits = {
            'gender':self.rng.choice(('男','女')),'domestic_scope':self.rng.choice(LOCATIONS),
            'family_finance':self.rng.choice(('家庭年收入20—30万元，预算安排较谨慎','家庭年收入30—50万元，可支持海外学习','家庭年收入50—80万元，重视课程质量')),
            'core_demand':'希望通过职业训练掌握实用技能，建立稳定的职业发展路径' if de else '希望提升学历背景和英语沟通能力，拓宽后续升学及就业选择',
            'further_study':'完成语言学习后申请适合自身背景的海外学习项目',
            'employment':'关注实践训练、行业发展和毕业后的就业方向',
            'admission':'愿意参加语言、面试和学习能力测评',
            'overseas_intent':'已与家人讨论，计划在下一学年进入海外学习阶段',
            'policy_attention':'关注签证申请材料与毕业后就业政策，申请前需再次核实',
            'immigration':'现阶段以学习和职业能力提升为主，暂无明确移民计划',
            'skill':'有较好的实践兴趣，希望加强专业技能训练',
            'language_ability':language,
            'family_support':'父母支持，家庭已预留语言学习和第一学年生活预算',
            'cost_sense':'希望分阶段核对费用，关注总预算及奖助机会',
            'learning_attitude':'接受系统训练，愿意执行每周语言学习计划',
            'hands_on':'愿意参加课程实践及项目训练','logical_thinking':'能够理解基础数理逻辑，希望通过练习进一步提升',
            'tag_weight':{'留学意愿':0.88,'学习主动性':0.82,'家庭支持':0.9},
        }
        return dict(name=name,phone=phone,age=age,education=education,project=project,major=major,traits=traits)

    def make_visitor(self, person, created):
        visitor = self.add('visitor_account',username=person['phone'],name=person['name'],nickname=person['name'],
            contact=person['phone'],password_hash=self.password_hash,created_at=created)
        person.update(visitor_id=visitor,registered=created)
        self.people.append(person)
        return visitor

    def make_lead(self, p, advisor, created, status):
        traits = p['traits']
        changed = min(self.now-timedelta(hours=1),created+timedelta(days=self.rng.randint(3,18)))
        last_contact = changed if status != 'new' else None
        lost = '家庭调整升学时间，暂缓本年度申请' if status == 'lost' else None
        lead_id = self.add('crm_lead',customer_name=p['name'],contact_info=p['phone'],
            gender='M' if traits['gender']=='男' else 'F',age=p['age'],education_level=p['education'],
            education_stage='graduated',intended_country='Germany' if p['project']=='de_vocational' else 'Singapore',
            intended_major=p['major'],intended_project=p['project'],background_info=traits['core_demand'],
            portrait=traits,profile_version=1,source_channel=self.rng.choice(CHANNELS),status=status,
            owner_employee_id=advisor['id'],last_contact_time=last_contact,lost_reason=lost,
            remark='关注语言准备、入学评估、费用安排及行前支持。',create_time=created,update_time=changed)
        p.update(lead_id=lead_id,advisor=advisor,status=status,created=created,updated=changed)
        self.leads.append(p)
        chain = ['new'] if status=='new' else ['new','contacting'] if status=='contacting' else ['new','contacting','qualified'] if status=='qualified' else ['new','contacting','qualified',status]
        interval=(changed-created)/max(1,len(chain)-1)
        for i,step in enumerate(chain):
            self.add('crm_lead_status_event',lead_id=lead_id,status=step,occurred_at=created+interval*i,reason=lost if step=='lost' else None)
        if p.get('visitor_id'):
            self.add('visitor_intake',visitor_id=p['visitor_id'],advisor_id=advisor['id'],claimed_at=created,last_contact_at=last_contact,crm_lead_id=lead_id)
        if status!='new':
            descriptions=(
                f"与{p['name']}完成首次电话沟通，确认目前学历和{PROJECT_LABELS[p['project']]}意向。",
                f"已向{p['name']}发送语言学习安排及材料清单，家庭将共同核对费用预算。",
                f"核对{p['name']}的学习计划与申请时间，下一步安排语言测评并完善个人资料。",
            )
            for i,body in enumerate(descriptions[:min(3,len(chain)-1)]):
                ts=created+interval*(i+1)
                self.add('crm_follow_up',lead_id=lead_id,employee_id=advisor['id'],follow_type=('phone','wechat','meeting')[i],
                    content=body,next_plan='核对语言测评结果及材料完成情况',create_time=ts)
                if p.get('visitor_id'):
                    self.add('visitor_call',visitor_id=p['visitor_id'],advisor_id=advisor['id'],request_id=secrets.token_hex(16),notes=body,recorded_at=ts)
        if status in ('qualified','signed'):
            self.add('crm_customer_identity',lead_id=lead_id,verified_name=p['name'],verified_mobile=p['phone'],verified_by=self.admin['id'],verified_at=changed)
        self.material_and_screening(p,created+timedelta(hours=2))
        return lead_id

    def material_and_screening(self, p, created):
        traits=p['traits']
        fields={'customer_name':p['name'],'age':p['age'],'gender':traits['gender'],'education_stage':'graduated','intended_major':p['major']}
        text_traits={**traits,'education':EDUCATION_LABELS[p['education']]+'，已毕业'}
        document=screening_document(f"U_{p.get('visitor_id') or p['lead_id']}",fields,text_traits,project_label=PROJECT_LABELS[p['project']])
        raw=json.dumps([{**document[0],'mobile':p['phone']}],ensure_ascii=False,indent=2)
        source=self.add('customer_source',source_type='import',raw_content=raw,file_name=p['name']+'个人资料.json',
            file_content=raw.encode('utf-8'),parse_status='success',lead_id=p['lead_id'],operator_id=p['advisor']['id'],
            parse_result={'customer_id':p['lead_id'],'confirmed_fields':{**traits,'age':p['age'],'education_level':p['education'],'education_stage':'graduated','intended_project':p['project'],'intended_major':p['major']},
                          'ownership':{'basis':'matched_identity','matched_fields':['name','mobile'],'confirmed_by_kind':'employee','confirmed_by_id':p['advisor']['id'],'confirmed_at':created.isoformat()}},create_time=created)
        if p.get('visitor_id'):
            self.add('visitor_material',source_id=source,visitor_id=p['visitor_id'])
        if p['status']=='new':
            return
        checked=ScreeningInput(project=p['project'],age=p['age'],education=p['education'],education_stage='graduated')
        screened=screen_profile(checked)
        findings=portrait_findings(p['project'],text_traits)
        official=screened.model_copy(update={'findings':(*screened.findings,*findings)})
        data={'input':checked.model_dump(mode='json'),'input_snapshot':document,'rule_version':RULE_VERSION,
              'screening':official.model_dump(mode='json'),'ai':{'state':'unavailable','message':'点击重新研判可生成最新的顾问建议和客户沟通话术。'}}
        profile=self.add('customer_profile',customer_name=p['name'],contact_info=p['phone'],source_id=source,
            lead_id=p['lead_id'],profile_version=1,background_info=data,match_result='matched' if screened.status.value=='potential_match' else 'partial',
            matched_product=PROJECT_LABELS[p['project']],match_reason='；'.join(official.findings),evaluator_id=p['advisor']['id'],create_time=created,update_time=created)
        self.c.execute(update(self.table('crm_lead')).where(self.table('crm_lead').c.id==p['lead_id']).values(customer_profile_id=profile,update_time=p['updated']))

    def people_and_customers(self):
        student_role=self.c.scalar(text("SELECT id FROM sys_role WHERE role_code='student'"))
        for i in range(42):
            cls=self.classes[i%len(self.classes)]
            p=self.person(i,cls['project'])
            if cls['project']=='de_vocational':
                p['traits']['language_ability']='德语B1，继续强化口语与面试表达' if 'B1' in cls['name'] else '德语A2，按计划准备B1阶段测评'
            enrolled=self.day-timedelta(days=self.rng.randint(45,80))
            registered=self.at(enrolled-timedelta(days=self.rng.randint(25,45)),self.rng.randint(0,10),self.rng.randint(0,59))
            self.make_visitor(p,registered)
            advisor=self.advisors[i%len(self.advisors)]
            self.make_lead(p,advisor,registered+timedelta(days=self.rng.randint(1,3)),'signed')
            student=self.add('sys_user',username=p['phone'],password_hash=self.password_hash,real_name=p['name'],user_type='student',
                role_id=student_role,department='国际升学项目',contact_info=p['phone'],status='normal',create_time=self.at(enrolled),update_time=self.now)
            self.add('student_info',user_id=student,student_no=f'YJ{enrolled.year}{i+1:04d}',school='粤教升学服务中心',major=p['major'],
                grade=f'{enrolled.year}级',abroad_country='Germany' if p['project']=='de_vocational' else 'Singapore',
                class_teacher_id=cls['teacher']['id'],enroll_date=enrolled,status='active',create_time=self.at(enrolled),update_time=self.now)
            self.add('website_student_access',visitor_id=p['visitor_id'],student_id=student,enabled=True)
            self.add('student_class_enrollment',student_id=student,class_id=cls['id'])
            self.add('class_placement_history',student_id=student,from_class_id=None,to_class_id=cls['id'],actor_id=cls['teacher']['id'],
                reason='根据入学语言测评与升学计划安排班级',changed_at=self.at(enrolled))
            p.update(student_id=student,cls=cls,enrolled=enrolled)
            self.students.append(p)
            self.accounts.append({'kind':'学生','name':p['name'],'username':p['phone'],'visitor_id':p['visitor_id'],'student_id':student,'lead_id':p['lead_id'],'class':cls['name'],'advisor':advisor['real_name']})
        for i in range(42,82):
            p=self.person(i)
            registered=self.at(self.day-timedelta(days=self.rng.randint(5,55)),self.rng.randint(0,12),self.rng.randint(0,59))
            self.make_visitor(p,registered)
            advisor=self.advisors[(i-42)%len(self.advisors)]
            status=self.rng.choices(('new','contacting','qualified','signed','lost'),weights=(12,35,30,15,8))[0]
            self.make_lead(p,advisor,registered+timedelta(days=1),status)
            self.accounts.append({'kind':'注册客户','name':p['name'],'username':p['phone'],'visitor_id':p['visitor_id'],'lead_id':p['lead_id'],'advisor':advisor['real_name']})
        for i in range(82,110):
            p=self.person(i)
            registered=self.at(self.day-timedelta(days=self.rng.randint(0,21)),self.rng.randint(0,10),self.rng.randint(0,59))
            self.make_visitor(p,registered)
            self.add('cs_visitor_profile',visitor_id=p['visitor_id'],display_name=p['name'],destinations='Germany' if p['project']=='de_vocational' else 'Singapore',
                education=EDUCATION_LABELS[p['education']],education_stage='graduated',interests=p['major'],summary='已提供学历背景和学习意向，等待顾问进一步沟通。',updated_at=registered,
                attributes={**p['traits'],'age':p['age'],'education_level':p['education'],'education_stage':'graduated','intended_project':p['project'],'intended_major':p['major'],'_version':1})
            self.accounts.append({'kind':'待认领访客','name':p['name'],'username':p['phone'],'visitor_id':p['visitor_id']})
        for i in range(110,152):
            p=self.person(i)
            created=self.at(self.day-timedelta(days=self.rng.randint(3,70)),self.rng.randint(0,10),self.rng.randint(0,59))
            status=self.rng.choices(('new','contacting','qualified','signed','lost'),weights=(18,30,30,12,10))[0]
            self.make_lead(p,self.advisors[(i-110)%len(self.advisors)],created,status)
        self.add('report_status_history_start',id=1,start_day=min(p['created'].date() for p in self.leads))

    def student_records(self):
        for i,p in enumerate(self.students):
            sid,cls=p['student_id'],p['cls']
            for course in cls['courses']:
                for exam in range(3):
                    day=self.day-timedelta(days=(35,21,7)[exam]+i%3)
                    score=max(48,min(98,self.rng.randint(61,86)+exam*3-(12 if i%13==0 else 0)))
                    row={'student_id':sid,'course_name':course,'score':score,'semester':f'{self.day.year}-{self.day.year+1}-1','credit':2.0,
                         'recorded_by':cls['teacher']['id'],'create_time':self.at(day),'exam_key':f'{self.courses[course]}:stage-{exam+1}',
                         'version':1,'update_time':self.at(day),'course_id':self.courses[course],
                         'study_stage':'preparatory' if course=='数学与逻辑基础' else 'overseas' if course=='学术阅读与写作' else 'language'}
                    score_id=self.add('student_score',**row)
                    after={k:v.isoformat() if isinstance(v,datetime) else v for k,v in row.items()}
                    self.add('student_score_history',score_id=score_id,version=1,operation='create',changed_by=cls['teacher']['id'],change_reason='阶段测评成绩录入',after_data=after,create_time=self.at(day))
            school='柏林应用技术大学' if p['project']=='de_vocational' else '新加坡管理学院'
            stage=('document_prep','submitted','under_review','offer_received','visa_processing','enrolled')[i%6]
            next_action={'document_prep':'补充毕业证明及语言学习记录','submitted':'核对申请回执并等待材料审核','under_review':'跟进材料审核结果并准备面试','offer_received':'核对录取通知要求及接受截止日期','visa_processing':'整理签证申请材料及资金证明','enrolled':'确认注册安排及行前准备清单'}[stage]
            self.add('application_progress',student_id=sid,target_school=school,target_major=p['major'],stage=stage,
                progress_detail=f"{p['name']}已完成当前阶段材料核对，顾问与班主任共同跟进后续安排。",
                deadline=self.day+timedelta(days=12+i%20),next_action=next_action,handler_id=p['advisor']['id'],create_time=self.at(p['enrolled']),update_time=self.now)
            for kind,title,days,study_stage in (
                ('exam','阶段语言能力测评',7+i%10,'language'),
                ('application','下一学年申请材料确认',20+i%15,'overseas'),
                ('paper','学习计划与个人陈述初稿',4+i%12,'preparatory'),
            ):
                self.add('academic_deadline',student_id=sid,deadline_type=kind,title=title,description='请在截止前完成并提交班主任核对。',deadline=datetime.combine(self.day+timedelta(days=days),time(9)),
                    reminder_enabled=1,reminder_days=[7,3,1],status='pending',study_stage=study_stage,create_time=self.now,update_time=self.now)
            for j in range(2 if i%3==0 else 1):
                status=('pending','approved','approved','rejected','cancelled')[(i+j)%5]
                start=self.at(self.day-timedelta(days=3+i%20)) if status!='pending' else datetime.combine(self.day+timedelta(days=1+i%4),time(1))
                end=start+timedelta(hours=4)
                created=min(start-timedelta(days=1),self.now-timedelta(hours=3))
                leave=self.add('student_admin_service',student_id=sid,service_type='leave',leave_type='personal' if i%2 else 'sick',start_time=start,end_time=end,
                    reason='预约医院复查，需外出半天，课后会补齐课堂笔记。' if i%2==0 else '需到户籍所在地办理申请所需公证材料，申请半天事假。',status=status,
                    approver_id=cls['teacher']['id'],approval_comment='已核对事由，请及时补齐课程内容。' if status=='approved' else '请补充预约凭证后重新申请。' if status=='rejected' else None,
                    approval_time=min(self.now,created+timedelta(hours=3)) if status in ('approved','rejected') else None,create_time=created,update_time=self.now)
                if status=='pending':
                    self.add('todo_item',assignee_id=cls['teacher']['id'],todo_type='leave_approval',title=p['name']+'的请假申请待审批',description='请核对请假时间、事由及补课安排。',related_type='leave',related_id=leave,priority='medium',status='pending',due_time=self.now+timedelta(days=1),source_status='pending',create_time=created,update_time=self.now)
            if i%2==0:
                self.feedback(p,i)
            self.wellbeing(p,i)

    def feedback(self,p,i):
        status=('pending','processing','resolved','closed')[i//2%4]
        created=self.at(self.day-timedelta(days=2+i%16))
        bodies=(('learning','语言课作业反馈安排','最近两次课后口语练习的反馈较晚，希望能固定每周反馈时间。','已和任课老师沟通，改为每周二、周五集中反馈。'),
                ('company','材料核对预约协调','申请材料需家人配合准备，希望顾问能安排一次晚间线上核对。','已安排晚间视频沟通，家长和学生共同完成材料核对。'),
                ('learning','测评复习资料补充','阶段测评临近，希望能补充听力练习和错题讲解。','已发送听力练习及解析，并安排一次错题答疑。'))
        category,title,body,solution=bodies[i//2%3]
        ticket=self.add('student_feedback_ticket',student_id=p['student_id'],ticket_type='complaint',category=category,title=title,content=body,detail=body,
            status=status,priority='medium' if i%5 else 'high',assignee_id=p['cls']['teacher']['id'],solution=solution if status in ('resolved','closed') else None,
            satisfaction=5 if status=='closed' else 4 if status=='resolved' else None,is_notified=int(status in ('resolved','closed')),create_time=created,update_time=min(self.now,created+timedelta(days=1)))
        if status in ('pending','processing'):
            self.add('todo_item',assignee_id=p['cls']['teacher']['id'],todo_type='complaint_follow',title=p['name']+'的反馈待跟进',description=body,related_type='complaint',related_id=ticket,priority='high',status='pending',due_time=self.now+timedelta(days=2),source_status=status,create_time=created,update_time=self.now)

    def wellbeing(self,p,i):
        sid,teacher=p['student_id'],p['cls']['teacher']['id']
        self.add('report_wellbeing_consent',student_id=sid,granted=1,version='v1',updated_at=self.at(p['enrolled']))
        records=[]
        for offset in range(56):
            day=self.day-timedelta(days=offset)
            if day<p['enrolled'] or self.rng.random()<0.15: continue
            concern=i in (4,17,30) and offset<6
            emotion='poor' if concern else self.rng.choices(('good','fair','poor'),weights=(70,27,3))[0]
            stress='high' if concern else 'moderate' if emotion=='fair' else 'light'
            self.add('report_wellbeing_checkin',student_id=sid,day=day,emotion=emotion,stress=stress,updated_at=self.at(day,11))
            if offset%7==0:
                score=self.rng.randint(43,58) if concern else self.rng.randint(72,93)
                body='近期测评压力较大，担心语言进度，愿意与班主任讨论复习节奏。' if concern else self.rng.choice(('本周能按计划完成学习任务，与同学交流顺利。','已适应课程节奏，希望继续提高口语表达。','近期作业较多，调整休息后状态稳定。'))
                self.add('student_psych_record',student_id=sid,emotion_tag='焦虑' if concern else '平稳',emotion_score=score,interaction_content=body,trigger_keywords=['测评压力'] if concern else [],record_date=day,create_time=self.at(day,11))
                records.append((day,score,body))
        if records:
            day,score,body=max(records)
            self.add('student_psych_profile',student_id=sid,latest_emotion_tag='焦虑' if i in (4,17,30) else '平稳',emotion_score=score,last_interaction_time=self.at(day,11),risk_level='medium' if i in (4,17,30) else 'low',weekly_summary={'summary':body},create_time=self.now,update_time=self.now)
        if i in (4,17,30):
            created=self.at(self.day-timedelta(days=3))
            self.add('student_psych_alert',student_id=sid,trigger_reason='连续多日反映语言测评压力，需要班主任了解近期学习与休息情况。',risk_level='medium',status='following',teacher_id=teacher,
                follow_record='已与学生进行一次个别沟通，协商降低每日练习量并增加同伴练习，三天后再次了解状态。',create_time=created,update_time=self.now)
            case=self.add('report_wellbeing_case',student_id=sid,status='open',note='语言测评前压力上升，安排学习节奏调整与持续沟通。',assigned_to=teacher,created_at=created)
            self.add('report_wellbeing_followup',case_id=case,actor_id=teacher,note='学生愿意执行调整后的复习计划，已约定下次沟通时间。',created_at=min(self.now,created+timedelta(days=1)))

    def activities(self):
        specs=(('德国双元制升学与职业规划说明会',7,'hybrid'),('新加坡升学路径与材料准备讲座',12,'online'),
               ('秋季语言学习体验开放日',18,'offline'),('家长沟通会：申请季时间与预算安排',-7,'online'),
               ('德语B1学习方法与面试准备分享',-21,'hybrid'),('新加坡留学行前准备交流会',-35,'offline'))
        for index,(name,days,kind) in enumerate(specs):
            start=datetime.combine(self.day+timedelta(days=days),time(6))
            event=self.add('event_lecture',event_name=name,event_type=kind,description='围绕学习规划、语言准备、材料核对和家校沟通进行交流，现场提供提问与咨询时间。',
                start_time=start,end_time=start+timedelta(hours=2),location='广州教学中心多功能教室' if kind!='online' else '线上会议室（报名后查看参会安排）',max_participants=40,
                current_participants=0,organizer_id=self.advisors[index%len(self.advisors)]['id'],status='upcoming' if days>0 else 'ended',is_published=1,create_time=min(start-timedelta(days=20),self.now),update_time=self.now)
            candidates=[p for p in self.people if p['registered']<=min(start,self.now)-timedelta(days=1)]
            attendees=self.rng.sample(candidates,min(12+index,len(candidates)))
            active=0
            for j,p in enumerate(attendees):
                status='attended' if days<0 and j%5 else 'no_show' if days<0 else 'cancelled' if j==0 else 'registered'
                if status!='cancelled': active+=1
                created=max(p['registered'],min(start,self.now)-timedelta(days=self.rng.randint(1,5)))
                self.add('event_registration',event_id=event,user_id=None,customer_id=p['visitor_id'],customer_name=p['name'],contact_info=p['phone'],status=status,
                    remark='希望了解语言准备及申请材料要求。',create_time=created,cancelled_at=min(self.now,created+timedelta(hours=1)) if status=='cancelled' else None,
                    attended_at=start if status=='attended' else None,checked_in_by=self.advisors[index%len(self.advisors)]['id'] if status=='attended' else None)
            self.c.execute(update(self.table('event_lecture')).where(self.table('event_lecture').c.id==event).values(current_participants=active))
            self.events.append(event)

    def reports_and_notifications(self):
        active=[s for s in self.staff if s['status']=='normal']
        for staff in active:
            if staff['role_code']=='admin': continue
            owned=[p for p in self.leads if p['advisor']['id']==staff['id']]
            roster=[p for p in self.students if p['cls']['teacher']['id']==staff['id']]
            role=staff['role_code']
            for offset in range(42):
                day=self.day-timedelta(days=offset)
                if day.weekday()>4: continue
                relevant=[p for p in owned if p['created'].date()<=day]
                if role=='employee':
                    selected=relevant[offset%len(relevant)] if relevant else None
                    content=f"完成{selected['name']}的{PROJECT_LABELS[selected['project']]}资料核对，沟通语言准备和申请时间。" if selected else '整理本周公开咨询渠道，梳理新客户资料接收清单。'
                    progress='更新客户个人资料，确认本周语言测评与家庭沟通安排。'
                    plan='回访意向客户，核对材料补充情况并记录下一步安排。'
                elif role=='team_leader':
                    selected=roster[offset%len(roster)] if roster else None
                    content=f"完成{selected['cls']['name']}的课堂答疑，核对{selected['name']}的练习进度。" if selected else '整理课程学习反馈，核对学生测评及请假安排。'
                    progress='完成作业反馈与阶段学习记录，更新需个别沟通的学生名单。'
                    plan='跟进阶段测评复习，核对缺课学生的补课计划。'
                else:
                    content='核对本周顾问跟进进度、客户资料质量和教学衔接安排。'
                    progress='梳理各顾问待推进客户，协调语言测评和家长沟通时段。'
                    plan='复核重点客户申请节点，组织顾问与班主任的进度同步。'
                risk='部分家庭仍在核对预算，需在下一次沟通中明确申请优先级。' if offset%5==0 else '暂无新增紧急事项，持续关注材料与语言准备进度。'
                self.add('employee_daily_report',employee_id=staff['id'],report_date=day,raw_content=content,content=content,
                    key_progress=[progress],risks=[risk],next_plan=plan,status='submitted',create_time=self.at(day,10))
            for week in range(8):
                start=self.day-timedelta(days=self.day.weekday()+week*7)
                self.add('employee_weekly_submission',employee_id=staff['id'],week_start=start,
                    content=f'{start:%m月%d日}所在周，围绕客户资料、语言学习和申请准备完成跨岗位协同。',
                    key_progress=progress,risks='关注客户材料补充时效与学生测评前的学习压力。',next_plan=plan,
                    submitted_at=self.at(min(start+timedelta(days=4),self.day),10))
            self.add('notification_log',user_id=staff['id'],notification_type='system',title='本周业务资料与教学安排已更新',
                content='请核对本人负责的客户资料、学生学习节点及待办事项。',channel='system',status='sent',create_time=self.now)
        for p in self.leads:
            if p['status'] in ('contacting','qualified'):
                self.add('todo_item',assignee_id=p['advisor']['id'],todo_type='custom',title='跟进'+p['name']+'的材料与测评安排',
                    description='核对家庭沟通结果、语言学习安排与材料完成情况。',related_type='crm_lead',related_id=p['lead_id'],priority='high' if p['status']=='qualified' else 'medium',
                    status='pending',due_time=self.now+timedelta(days=self.rng.randint(1,5)),create_time=self.now,update_time=self.now)

    def validate(self):
        errors=[]
        for table in self.m.tables.values():
            for constraint in table.foreign_key_constraints:
                pairs=[(e.parent,e.column) for e in constraint.elements]
                condition=' AND '.join(f'c.`{left.name}`=p.`{right.name}`' for left,right in pairs)
                present=' AND '.join(f'c.`{left.name}` IS NOT NULL' for left,_ in pairs)
                query=f'SELECT COUNT(*) FROM `{table.name}` c LEFT JOIN `{pairs[0][1].table.name}` p ON {condition} WHERE {present} AND p.`{pairs[0][1].name}` IS NULL'
                count=self.c.scalar(text(query))
                if count: errors.append(f'{table.name}.{constraint.name}: {count} broken references')
        checks={
            'student_account_and_profile':"SELECT COUNT(*) FROM website_student_access a JOIN visitor_account v ON v.id=a.visitor_id JOIN sys_user u ON u.id=a.student_id JOIN visitor_intake i ON i.visitor_id=v.id JOIN crm_lead l ON l.id=i.crm_lead_id WHERE v.name COLLATE utf8mb4_unicode_ci<>u.real_name OR v.name COLLATE utf8mb4_unicode_ci<>l.customer_name OR v.contact COLLATE utf8mb4_unicode_ci<>u.contact_info OR v.contact COLLATE utf8mb4_unicode_ci<>l.contact_info OR l.status<>'signed'",
            'class_teacher_country':"SELECT COUNT(*) FROM student_info s JOIN student_class_enrollment e ON e.student_id=s.user_id JOIN project_class c ON c.id=e.class_id JOIN teaching_project t ON t.project_id=c.project_id WHERE s.class_teacher_id<>c.teacher_id OR s.abroad_country<>t.abroad_country",
            'visitor_owner':"SELECT COUNT(*) FROM visitor_intake i JOIN crm_lead l ON l.id=i.crm_lead_id WHERE i.advisor_id<>l.owner_employee_id",
            'event_capacity':"SELECT COUNT(*) FROM event_lecture e WHERE e.current_participants<>(SELECT COUNT(*) FROM event_registration r WHERE r.event_id=e.id AND r.status<>'cancelled') OR e.current_participants>e.max_participants",
            'future_registration':"SELECT COUNT(*) FROM visitor_account WHERE created_at>UTC_TIMESTAMP()",
            'future_reports':"SELECT COUNT(*) FROM employee_daily_report WHERE report_date>UTC_DATE() OR create_time>UTC_TIMESTAMP()",
            'future_events':"SELECT COUNT(*) FROM crm_lead_status_event WHERE occurred_at>UTC_TIMESTAMP()",
            'score_course':"SELECT COUNT(*) FROM student_score s JOIN student_class_enrollment e ON e.student_id=s.student_id LEFT JOIN class_course c ON c.class_id=e.class_id AND c.course_id=s.course_id WHERE c.course_id IS NULL",
            'lead_profile':"SELECT COUNT(*) FROM crm_lead l JOIN customer_profile p ON p.id=l.customer_profile_id WHERE p.lead_id<>l.id OR p.profile_version<>l.profile_version",
            'followup_order':"SELECT COUNT(*) FROM crm_follow_up f JOIN crm_lead l ON l.id=f.lead_id WHERE f.create_time<l.create_time OR f.create_time>UTC_TIMESTAMP()",
        }
        for label,query in checks.items():
            count=self.c.scalar(text(query))
            if count: errors.append(f'{label}: {count}')
        patterns=('联调','QA-V11','QA客户','测试员工','验证顾问','本地测试','ENT_LOCAL_VERIFY','占位')
        fields={'sys_user':('real_name','department','username'),'visitor_account':('name','nickname'),
                'course_project':('project_name','description'),'teaching_course':('name','institution'),
                'project_class':('name',),'sys_organization':('org_name',),'crm_lead':('customer_name','remark','background_info'),
                'crm_follow_up':('content',),'employee_daily_report':('content',),'employee_weekly_submission':('content',)}
        for name,columns in fields.items():
            for row in self.c.execute(select(*(self.table(name).c[k] for k in columns))):
                if any(marker in str(value) for value in row for marker in patterns):
                    errors.append(f'{name}: leftover placeholder text')
                    break
        assert len(self.students)==42 and len(self.people)==110 and len(self.leads)==124
        if errors: raise RuntimeError(json.dumps(errors,ensure_ascii=False))
        return {'foreign_keys':'passed','identity_inheritance':'passed','class_teacher_country':'passed','event_capacity':'passed','chronology':'passed','placeholder_scan':'passed'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    parser.add_argument('--backup',type=Path,required=True,help='Directory with verified dump and manifest.json')
    args=parser.parse_args()
    engine,settings=_engine()
    if settings.db_name!='education_service': raise SystemExit('Expected explicitly authorized local database education_service')
    manifest=json.loads((args.backup/'manifest.json').read_text(encoding='utf-8'))
    dump=Path(manifest['dump'])
    if manifest['database']!=settings.db_name or manifest['sha256']!=hashlib.sha256(dump.read_bytes()).hexdigest():
        raise SystemExit('Backup integrity verification failed')
    metadata=MetaData()
    metadata.reflect(engine)
    if set(metadata.tables)!=set(manifest['row_counts']): raise SystemExit('Schema changed after backup')
    with engine.connect() as conn:
        if conn.scalar(text("SELECT GET_LOCK('education_service_showcase_refresh',0)"))!=1: raise SystemExit('Another refresh is running')
        conn.commit()
        try:
            with conn.begin():
                s=Showcase(conn,metadata,utc_now())
                print('Preparing business records; transaction is not committed.',flush=True)
                s.clear_business()
                s.staff_and_organizations()
                s.teaching()
                s.operating_guides()
                s.people_and_customers()
                s.student_records()
                s.activities()
                s.reports_and_notifications()
                checks=s.validate()
                counts={name:conn.scalar(select(func.count()).select_from(table)) for name,table in metadata.tables.items()}
                if args.apply:
                    s.add('ent_auth_audit',actor_id=s.admin['id'],action='业务资料重建',target=settings.db_name,
                        details=json.dumps({'source':'合成业务展示资料','backup':str(args.backup),'visitors':110,'students':42,'customers':124,'classes':6},ensure_ascii=False),create_time=s.now)
                else:
                    conn.rollback()
            summary={'applied':args.apply,'database':settings.db_name,'data_kind':'synthetic_realistic','backup':str(args.backup),'checks':checks,'row_counts':counts,
                     'visitors':110,'unclaimed':28,'customers':124,'students':42,'classes':6,'staff':len(s.staff),'teachers':len(s.teachers),'advisors':len(s.advisors)}
            if args.apply:
                path=ROOT/'logs/showcase-accounts.json'
                path.write_text(json.dumps({'data_kind':'synthetic_realistic','website_password':s.password,'accounts':s.accounts,
                    'staff_existing_credentials_unchanged':[{'id':v['id'],'name':v['real_name'],'username':v['username'],'role':v['role_code']} for v in s.staff if v['status']=='normal']},ensure_ascii=False,indent=2),encoding='utf-8')
                (ROOT/'logs/showcase-refresh-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
                print('Website credentials saved locally: '+str(path),flush=True)
            else:
                (ROOT/'logs/showcase-dry-run.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({k:v for k,v in summary.items() if k!='row_counts'},ensure_ascii=False,indent=2),flush=True)
        finally:
            conn.execute(text('SET @base_org_actor_user_id = NULL'))
            conn.execute(text("SELECT RELEASE_LOCK('education_service_showcase_refresh')"))
            conn.commit()


if __name__=='__main__':
    main()
