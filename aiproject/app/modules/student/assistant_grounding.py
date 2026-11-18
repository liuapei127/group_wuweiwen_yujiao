"""Concrete checks for model wording based on server-selected, owned evidence.

This is a bounded fact guard, not a general semantic entailment classifier.
Prompts, curated evidence and regression evaluation remain necessary.
"""
from __future__ import annotations

import re

from app.core.exceptions import BusinessError


_NUMBER = re.compile(r"\d+(?:[.:/-]\d+)*")
_QUANTITY = re.compile(r"(?:\d+(?:\.\d+)?|[零〇一二两三四五六七八九十百千万]+)\s*(?:分钟|小时|天|周|个月|岁|欧元|新元|新币|美元|英镑|元|公里)")
_ENUMERATION = re.compile(r"(?m)^\s*\d{1,2}[.、)]\s+|第\d{1,2}步")
_UNKNOWN = re.compile(r"^(?:未登记|尚未登记|没有登记|暂无|未提供|未填写|不清楚|未知|尚未分配|没有记录|未设置)")
_LABELS = {
    "学籍姓名": ("student_name",), "正式姓名": ("student_name",),
    "姓名": ("student_name",), "名字": ("student_name", "preferred_name"),
    "昵称": ("preferred_name",), "称呼": ("preferred_name",),
    "班主任老师": ("class_teacher",), "班主任": ("class_teacher",), "负责老师": ("class_teacher",), "老师": ("class_teacher",),
    "当前就读院校": ("school",), "学校": ("school",), "院校": ("school",),
    "专业": ("major",), "学号": ("student_no",), "所属项目": ("project_name",), "项目": ("project_name",),
    "当前班级": ("class_name",), "班级": ("class_name",),
    "留学去向": ("abroad_country",), "留学方向": ("abroad_country",),
    "留学国家": ("abroad_country",), "留学地区": ("abroad_country",),
    # These fields are not part of the selected student assistant profile.
    "年龄": (), "性别": (), "生日": (), "出生日期": (), "地址": (), "住址": (),
}
_LABEL = "|".join(sorted(_LABELS, key=len, reverse=True))
_CLAIM = re.compile(r"(?P<label>" + _LABEL + r")(?:是|为|叫|[:：])\s*(?P<value>[^，。！？；\n]{1,100})")
_REVERSE_CLAIM = re.compile(r"(?:^|[，。！？；\n])(?P<value>[^，。！？；\n]{1,60}?)(?:是|为)你(?:的)?(?P<label>" + _LABEL + r")")
_NAME_CLAIM = re.compile(r"你(?:名叫|叫|是)(?P<value>[^，。！？；\n]{1,60})")
_GREETING = re.compile(r"^(?:你好|嗨)[，,]\s*(?P<value>[\u4e00-\u9fff]{2,8})(?=[，,。！!]|$)")
_PREFERENCE = re.compile(r"你(?:之前|以前)?(?:希望|让我|要我)(?:我)?(?:叫你|称呼你(?:为)?)(?P<value>[^，。！？；\n]{1,40})")
_NEGATED_NAME = re.compile(r"你(?:不是|并非|不叫)(?P<value>[^，。！？；\n]{1,60})")
_NEGATED_FIELD = re.compile(r"(?P<label>" + _LABEL + r")(?:不是|并非|不叫)(?P<value>[^，。！？；\n]{1,100})")
_PERSONAL_INTRO = re.compile(
    r"^(?:你好|嗨|好的|当然|可以|嗯|是的|"
    r"(?:我)?(?:看|查看|查阅|核对)(?:了(?:一下)?|过|一下)?(?:你的|当前|这份|账号)(?:资料|档案|学籍)(?:信息)?|"
    r"根据(?:你的|当前)?(?:学籍|档案|资料|登记)(?:信息|记录)?(?:来看)?|"
    r"(?:这是|这些是|以上是)(?:你的|当前账号的)?(?:学籍|档案|登记)(?:资料|信息|记录))$"
)
_PERSONAL_ADVICE = re.compile(r"^(?:如果(?:资料|信息)有误|如需(?:更正|核对)|如果需要(?:更正|核对)|"
                              r"(?:请|可以)(?:联系|向)(?:班主任|负责老师|教务老师|老师)(?:核对|确认|更正|补充)|"
                              r"还想(?:了解|查看)|(?:这个|聊天中的)?称呼(?:不会|不代表))")
_TEACHER_HINT = re.compile(r"班主任|老师|教师|带你|负责(?:指导|带|教)|担任")
_NAMED_TEACHER = re.compile(r"([\u4e00-\u9fff]{1,8})(?:老师|教师)")
_TEACHER_PREFIX = re.compile(r"^(?:你的?|这位|一位|其他|学校|班主任|教务|任课|授课|负责|请|联系|询问|咨询|向|与|和|由|是|为)")
_LATIN_ENTITY = re.compile(r"(?<![A-Za-z0-9])[A-Za-z][A-Za-z0-9]*(?:[-+][A-Za-z0-9]+)*")
_ABSENT_KNOWLEDGE = re.compile(
    r"^(?:(?:当前|目前|现有|这份|所提供的)?(?:资料|内容|来源)(?:中|里)?"
    r"(?:没有|未|尚未|暂未)(?:说明|提及|提供|确认)|"
    r"(?:我|目前|我目前|暂时)?(?:无法|不能|尚不能)(?:确认|核实)|"
    r"(?:我|目前|我目前|暂时)?(?:不确定|不清楚)(?:是否|能否))"
)
_MIXED_RECOMMENDATION = re.compile(r"但是|但|不过|然而|所以|因此|建议|推荐|请|就去|可以|你能|支持")


def _missing_knowledge_disclosure(clause):
    # Only a standalone disclosure may mention an unverified product/channel.
    # 'If unsure, buy X' is advice, not evidence that X is available.
    clause = clause.strip()
    return bool(_ABSENT_KNOWLEDGE.match(clause) and not _MIXED_RECOMMENDATION.search(clause))

_TICKET_TYPES = re.compile(
    r"易通卡|万捷通|游客通行证|旅游通行证|游客卡|学生优惠卡|学生卡|储值卡|预付卡|"
    r"交通卡|公交卡|地铁卡|单程票|往返票|联程票|电子票|纸质票|月票|周票|日票"
)
_CHANNELS = re.compile(r"便利店|便利商店|邮局|超市|地铁站|车站|公交站|自动售票机|售票机|"
                       r"售票亭|售票处|售票窗口|客服中心|服务点|柜台|官网|网上|线上|官方应用|官方App", re.I)
_PURCHASE = re.compile(r"购买|购票|买票|买(?:车票|票)|售卖|出售|售票")
_TOP_UP = re.compile(r"充值|充钱|加值")
_SERVICE_QUALITY = re.compile(r"准点(?:率(?:高|低))?|准时|高效")
_BENEFIT = re.compile(r"更省事|更省钱|更便宜|更划算|最方便|最省钱|免费|享受优惠|享有优惠")


def _channel(value):
    return value.lower().replace("自动售票机", "售票机").replace("便利商店", "便利店").replace("官方app", "官方应用")


def _knowledge_claims(text, supported, country):
    """A request for detail does not authorize new products or sales outlets.

    Concrete names come only from answer bodies and curated steps. Metadata,
    URLs and student questions cannot turn model prior knowledge into a source.
    """
    latin = {value.casefold() for value in _LATIN_ENTITY.findall(supported)}
    if country in ("Germany", "Singapore"):
        latin.add(country.casefold())
    # DB is the established alias of Deutsche Bahn, not the DB Navigator app.
    # Official naming: https://www.deutschebahn.com/en/legal-6934532
    if country=="Germany" and "德国铁路" in supported:
        latin.add("db")
    if re.search(r"应用|App", supported, re.I):
        latin.add("app")
    if "地铁" in supported and country == "Singapore":
        latin.add("mrt")
    if "公交" in supported or "巴士" in supported:
        latin.add("bus")
    source_clauses = [part.strip() for part in re.split(r"[。！？；\n]", supported) if part.strip()]
    normalized_support = _channel(supported)
    for clause in re.split(r"[，,。！？；;\n]", text):
        if not clause.strip() or _missing_knowledge_disclosure(clause):
            continue
        if any(value not in supported for value in _SERVICE_QUALITY.findall(clause)):
            raise BusinessError(502,"回复增加了资料以外的服务质量评价")
        if any(value.casefold() not in latin for value in _LATIN_ENTITY.findall(clause)):
            raise BusinessError(502, "回复增加了资料以外的产品或机构名称")
        if any(value not in supported for value in _TICKET_TYPES.findall(clause)):
            raise BusinessError(502, "回复增加了资料以外的票种或卡片")
        for channel in _CHANNELS.findall(clause):
            generic_station = channel in ("地铁站", "车站", "公交站") and re.search(r"地铁|公交|巴士|进站|出站", supported)
            if _channel(channel) not in normalized_support and not generic_station:
                raise BusinessError(502, "回复增加了资料以外的服务渠道")
        for action in (_PURCHASE, _TOP_UP):
            if not action.search(clause):
                continue
            supporting = [part for part in source_clauses if action.search(part)]
            if not supporting:
                raise BusinessError(502, "资料未确认该购票或充值操作")
            for channel in _CHANNELS.findall(clause):
                if not any(_channel(channel) in _channel(part) for part in supporting):
                    raise BusinessError(502, "回复增加了未经确认的办理渠道")
        if any(value not in normalized_support for value in _BENEFIT.findall(_channel(clause))):
            raise BusinessError(502, "回复增加了资料以外的优惠或比较结论")


def _supported_personal_clauses(text, fields):
    """Do not emit a guessed personal assertion and discover it only at finish.

    A factual clause needs a selected value in that clause. A small set of
    harmless framing/advice clauses is allowed without turning it into fact
    evidence. This deliberately prefers a truthful fallback to unsupported
    paraphrases that cannot be tied to a supplied field.
    """
    values = [_compact(value) for value in _values(fields, tuple(fields))]
    teacher = _compact(fields.get("class_teacher"))
    for raw in re.split(r"[，,。！？；;\n]", text):
        clause = raw.strip()
        if not clause or _PERSONAL_INTRO.fullmatch(clause):
            continue
        advice = bool(_PERSONAL_ADVICE.search(clause))
        if _TEACHER_HINT.search(clause):
            if teacher:
                extra = re.search(re.escape(teacher) + r"(?:老师)?(?:和|与|及|、)([^，。！？；\n]{1,12}?)(?:共同负责|一起负责|负责|担任|带你)", clause)
                if extra and _compact(extra.group(1)).removesuffix("老师") != teacher:
                    raise BusinessError(502, "回复增加了资料以外的负责人员")
            # A correct teacher elsewhere in the sentence cannot launder an
            # extra named teacher such as '陆安然和王老师共同负责'.
            remaining = clause.replace(teacher, "") if teacher else clause
            for match in _NAMED_TEACHER.finditer(remaining):
                name = match.group(1)
                while stripped := _TEACHER_PREFIX.sub("", name, count=1):
                    if stripped == name:
                        break
                    name = stripped
                if name and not _TEACHER_PREFIX.fullmatch(name):
                    raise BusinessError(502, "回复包含资料以外的负责老师")
            if teacher and not advice and teacher not in clause:
                # A role-only clause referring to an unknown person is not
                # authorized merely because a correct name appears later.
                if re.search(r"负责|带你|担任|(?:是|为|叫)", clause):
                    raise BusinessError(502, "负责老师的说法缺少本人资料支持")
        if advice or any(value and value in clause for value in values):
            continue
        if re.search(r"未登记|尚未登记|没有登记|没有查到|暂未|暂无|未提供|未填写|未分配|未知", clause):
            missing = [label for label, keys in _LABELS.items()
                       if label in clause and keys and not _values(fields, keys)]
            if missing:
                continue
        raise BusinessError(502, "个人资料回复包含未能核实的说法")


def _compact(value):
    return re.sub(r"\s+", "", str(value or ""))


def _values(fields, keys):
    values = [str(fields[key]) for key in keys if fields.get(key) not in (None, "")]
    if "abroad_country" in keys:
        values += [{"Singapore": "新加坡", "Germany": "德国"}.get(value, value) for value in values]
    return values


def _matches(value, expected):
    value = _compact(value).strip('“”「」《》\"\'')
    for item in expected:
        candidate = _compact(item)
        if value == candidate or value in (candidate + "老师", candidate + "同学"):
            return True
    return False


def _personal_claims(text, fields, required_fields=()):
    # Formatting changes neither facts nor authority. Normalize it before
    # matching so spaces cannot conceal a fabricated field assertion.
    text = re.sub(r"[^\S\n]+", "", text).replace("*", "").replace("`", "")
    for match in _NEGATED_NAME.finditer(text):
        if _matches(match.group("value"), _values(fields, ("student_name", "preferred_name"))):
            raise BusinessError(502, "回复否定了已核实的学生身份")
    for match in _NEGATED_FIELD.finditer(text):
        if _matches(match.group("value"), _values(fields, _LABELS[match.group("label")])):
            raise BusinessError(502, "回复否定了已核实的学生字段")
    for pattern in (_CLAIM, _REVERSE_CLAIM):
        for match in pattern.finditer(text):
            keys = _LABELS[match.group("label")]
            if match.group("label") == "名字" and "student_name" in required_fields:
                keys = ("student_name",)
            expected = _values(fields, keys)
            value = match.group("value").strip()
            if not expected and _UNKNOWN.match(value):
                continue
            if not _matches(value, expected):
                raise BusinessError(502, "回复与已核实的学生字段不一致")
    for match in _NAME_CLAIM.finditer(text):
        value = match.group("value").strip()
        # Conversational paraphrases are not identity claims.
        if re.match(r"(?:想|在问|说|希望|指|需要|准备|否|不是|不想)", value):
            continue
        identity_keys = ("student_name",) if "student_name" in required_fields else ("student_name", "preferred_name")
        if not _matches(value, _values(fields, identity_keys)):
            raise BusinessError(502, "回复包含未经核实的学生身份")
    greeting = _GREETING.search(text)
    if greeting and not _matches(greeting.group("value"), _values(fields, ("student_name", "preferred_name"))):
        raise BusinessError(502, "回复包含未经核实的学生称呼")
    for match in _PREFERENCE.finditer(text):
        if not _matches(match.group("value"), _values(fields, ("preferred_name",))):
            raise BusinessError(502, "回复包含未经核实的称呼偏好")
    if fields:
        _supported_personal_clauses(text, fields)



def _report_phrase(text):
    text=re.sub(r'[\s「」“”"\'：:]+','',text)
    text=re.sub(r'^学生自述','',text)
    text=re.sub(r'^你(?:之前|以前)?(?:告诉我|说过|说)','',text)
    text=re.sub(r'^(?:我|你)(?:之前|以前)?','你',text)
    return text.replace('喜欢吃','喜欢').strip('。！!～~')


def _mask_self_reports(text, reports):
    """Match only explicit recalled user facts, never an assistant invention.

    An entire preference clause must match. A known apple preference cannot
    authorize an added banana preference in that same clause.
    """
    expected={_report_phrase(report) for report in reports}
    def replace(match):
        clause=match.group(0)
        if _report_phrase(clause) in expected:
            return '好的'
        if re.search(r'喜欢|偏好|习惯',clause):
            raise BusinessError(502,'回复增加或改变了学生自述偏好')
        return clause
    return re.sub(r'[^，,。！？；;\n]+',replace,text)


def check_grounded_reply(text, kind, evidence):
    """Check only server-owned fields/answer bodies, never claims in a question."""
    if not isinstance(evidence, dict):
        raise BusinessError(502, "回复缺少可信资料")
    if kind == "student_fact":
        fields = evidence.get("fields")
        if evidence.get("kind") != "student_record" or not isinstance(fields, dict) or not (fields or evidence.get("self_reports")):
            raise BusinessError(502, "回复缺少本人资料")
        supported = " ".join(str(value) for value in fields.values() if value is not None)
        reports=evidence.get("self_reports",[])
        if not isinstance(reports,list) or any(not isinstance(r,str) or not r.startswith("学生自述：") for r in reports):
            raise BusinessError(502,"回复缺少本人自述依据")
        supported+=" "+" ".join(reports)
        checked=_mask_self_reports(text,reports) if reports else text
        _personal_claims(checked, fields, evidence.get("required_fields", ()))
        if reports and not fields:
            _supported_personal_clauses(checked,{})
    elif kind == "grounded_knowledge":
        records = evidence.get("records")
        if evidence.get("kind") != "knowledge" or not isinstance(records, list) or not records:
            raise BusinessError(502, "回复缺少检索资料")
        pieces = []
        for row in records:
            if not isinstance(row, dict) or row.get("country") not in (None, evidence.get("country")):
                raise BusinessError(502, "知识资料地区不一致")
            for key in ("answer", "short_answer", "scope"):
                if isinstance(row.get(key), str):
                    pieces.append(row[key])
            pieces.extend(step for step in row.get("steps", []) if isinstance(step, str))
        supported = " ".join(pieces)
        if not supported.strip():
            raise BusinessError(502, "回复缺少可引用的知识正文")
        # Public knowledge cannot establish the student's school, teacher or name.
        _personal_claims(text, {})
        _knowledge_claims(text, supported, evidence.get("country"))
    else:
        raise BusinessError(502, "不支持的资料回复类型")
    if any(number not in set(_NUMBER.findall(supported)) for number in _NUMBER.findall(_ENUMERATION.sub("", text))):
        raise BusinessError(502, "回复包含资料以外的数字")
    if any(_compact(quantity) not in _compact(supported) for quantity in _QUANTITY.findall(text)):
        raise BusinessError(502, "回复包含资料以外的数量")


def check_required_fields(text, evidence):
    """Optional backend-selected essentials must survive final generation."""
    if not isinstance(evidence, dict) or evidence.get("kind") != "student_record":
        return
    fields = evidence.get("fields") or {}
    for key in evidence.get("required_fields", []):
        values = _values(fields, (key,))
        if values and not any(_compact(value) in _compact(text) for value in values):
            raise BusinessError(502, "回复未回答所问的学生字段")

    if evidence.get('memory_requested') and not evidence.get('self_reports'):
        if not re.search(r'(?:没有|尚未|还没|不清楚|不知道|未).*?(?:偏好|喜欢)|(?:记忆|偏好).*?(?:没有|还没|未知|未登记)',text):
            raise BusinessError(502,'回复遗漏了尚未记下的偏好说明')
    if evidence.get('memory_requested') and evidence.get('self_reports'):
        clauses=[_report_phrase(c) for c in re.split(r'[，,。！？；;\n]',text) if c.strip()]
        if not any(_report_phrase(report) in clauses for report in evidence['self_reports']):
            raise BusinessError(502,'回复没有回答所问的个人偏好')
