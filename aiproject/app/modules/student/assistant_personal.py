"""Question-sized, account-owned facts for natural replies and deterministic fallback."""
import re

_LABELS = {'class_teacher':'班主任','class_name':'班级','project_name':'所属项目','major':'专业','school':'当前登记院校','student_no':'学号','abroad_country':'留学方向'}
_COUNTRIES = {'Germany':'德国','Singapore':'新加坡'}
_NAME = re.compile(r'(?:我是谁|我叫什么(?:名字)?|我叫啥|我的(?:学籍姓名|正式姓名|姓名|名字)(?:是|叫)?(?:什么|啥)?|你(?:还)?(?:记得|知道|认识)我(?:叫什么(?:名字)?)?|我(?:之前)?(?:让|希望)你(?:怎么称呼我|叫我什么)|怎么称呼我|说说你对我的了解)')
_FIELD_PATTERNS = {
 'class_teacher':r'(?:我的(?:班主任|老师|负责老师)(?:是|叫)?(?:谁|什么名字|哪位)?|谁是我的班主任|哪位老师负责我)',
 'class_name':r'(?:我(?:目前|现在)?(?:在|属于)?(?:哪个|什么)班(?:级)?|我的(?:当前)?班级(?:是|叫)?(?:什么|啥|哪个)?)',
 'project_name':r'(?:我的(?:所属)?项目(?:是|叫)?(?:什么|啥)?|我(?:属于|参加|报名的)(?:哪个|什么)?项目)',
 'major':r'(?:我的(?:当前)?专业(?:是|叫)?(?:什么|啥)?|我(?:学|读)(?:的)?(?:什么|哪个)专业)',
 'school':r'(?:我的(?:当前)?(?:学校|院校)(?:是|叫)?(?:什么|哪所|哪个)?|我(?:目前|现在)?(?:在|就读于)?(?:哪所|哪个)(?:学校|院校))',
 'student_no':r'(?:我的学号(?:是|叫)?(?:什么|啥)?|我学号(?:是|叫)?(?:什么|啥))',
 'abroad_country':r'(?:我的留学(?:国家|去向|地区|方向)|我(?:目前|现在)?(?:在哪|在哪个|在哪国|去哪个|去什么)(?:国家)?留学)',
}

def _question(query):
    text=re.sub(r'[，,。！？?！\s]+$','',query.strip())
    text=re.sub(r'^(?:请问|请告诉我|告诉我|帮我查一下|我想知道)','',text)
    return re.sub(r'(?:吗|呢|呀|啊)$','',text)

_MEMORY_QUESTION = re.compile(r'(?:你(?:还)?(?:记得|知道)?(?:我)?|我)?(?:更?喜欢吃什么|喜欢喝什么|喜欢什么|有什么(?:喜好|偏好)|的(?:饮食偏好|喜好|偏好)(?:是)?什么)')


def _requests(query):
    """Only a complete set of owned questions may enter this read-only branch."""
    text=_question(query)
    clauses=re.split(r'[，,。？！?；;\s]+|还有|以及|顺便(?:问一下)?|并且|(?<=谁)和|(?<=什么)和',text)
    out=[]
    for clause in clauses:
        clause=_question(clause)
        if not clause:
            continue
        field=requested_field(clause)
        if field:
            out.append((field,clause))
        elif _NAME.fullmatch(clause):
            out.append(('identity',clause))
        elif _MEMORY_QUESTION.fullmatch(clause):
            out.append(('memory',clause))
        else:
            return []
    return out


def handles(query):
    return bool(_requests(query))


def requested_field(query):
    text=_question(query)
    return next((key for key,pattern in _FIELD_PATTERNS.items() if re.fullmatch(pattern,text)),None)


def summary_request(query):
    return bool(re.fullmatch(r'(?:(?:查|查看|看看|显示|打开|给我看|请给我看)(?:一下)?)?(?:我的)?(?:完整|全部|所有)?(?:学籍(?:资料|信息)?|资料|信息|档案)',_question(query)))


def _selected_memories(memories, question):
    from . import assistant_mem0
    food=bool(re.search(r'吃|喝|饮食',question))
    selected=[]
    for memory in memories:
        # The recall service has already applied account ownership. Recheck the
        # fact shape so an old assistant summary/question is never promoted.
        if (not isinstance(memory,str) or not memory.startswith('学生自述：')
                or assistant_mem0.memory_kind(memory)!='preference'
                or assistant_mem0._sensitive(memory)):
            continue
        body=memory.removeprefix('学生自述：').strip()
        if food and not re.search(r'吃|喝|饮食|食物|口味|素食',body):
            continue
        if memory not in selected:
            selected.append(memory)
    return selected[:2]


def answer(query, profile, *, preferred_name='', memories=()):
    profile=profile or {}
    requests=_requests(query)
    keys=[]
    identity=False
    memory_questions=[]
    for field,clause in requests:
        if field=='memory':
            memory_questions.append(clause)
        elif field=='identity':
            identity=True
            keys.append('student_name')
            if '我是谁' in clause:
                keys+=['project_name','major']
        else:
            keys.append(field)
    keys=list(dict.fromkeys(keys))
    fields={key:str(profile[key]) for key in keys if profile.get(key)}
    missing=[key for key in keys if not profile.get(key)]
    if identity and preferred_name:
        fields['preferred_name']=preferred_name
    reports=_selected_memories(memories,' '.join(memory_questions)) if memory_questions else []
    parts=[]
    if memory_questions:
        if reports:
            parts.append('你之前告诉我：'+ '「'+reports[0].removeprefix('学生自述：')+'」'+'。')
        else:
            parts.append('目前可用的记忆里还没有找到这项偏好，你可以告诉我。')
    if identity:
        name=fields.get('student_name')
        if name:
            parts.append(f'你的学籍姓名是{name}。')
            if fields.get('project_name'):parts.append(f'所属项目是{fields["project_name"]}。')
            if fields.get('major'):parts.append(f'专业是{fields["major"]}。')
            if preferred_name and preferred_name!=name:
                parts.append(f'你之前希望我称呼你为{preferred_name}。')
        elif preferred_name:
            parts.append(f'你之前希望我称呼你为{preferred_name}；当前学籍姓名尚未登记。')
        else:
            parts.append('当前账号的学籍姓名还没有登记，我也没有记下你希望使用的称呼。可以告诉我怎么称呼你。')
    for field,_ in requests:
        if field in ('identity','memory'):
            continue
        value=fields.get(field)
        if value:
            value=_COUNTRIES.get(value,value)
            parts.append(f'你的{_LABELS[field]}是{value}。' if field!='abroad_country' else f'你的学籍登记的留学方向是{value}，这不代表实时所在地。')
        else:
            parts.append(f'当前学籍还没有登记你的{_LABELS[field]}，可以请负责老师核对补充。')
    required=list(dict.fromkeys(field if field!='identity' else 'student_name' for field,_ in requests
                               if field!='memory' and fields.get(field if field!='identity' else 'student_name')))
    evidence={'kind':'student_record','question':query,'fields':fields,'missing_fields':missing,
              'required_fields':required,'self_reports':reports,'memory_requested':bool(memory_questions),
              'source':'当前账号的正式学籍与该账号本人自述分开提供；自述不修改正式学籍'}
    return {'intent':'profile','reply':''.join(parts),'facts_kind':'student_record','reply_evidence':evidence}
