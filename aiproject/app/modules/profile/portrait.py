"""客户画像保存通用事实，项目规则选择所需属性。"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Trait:
    key: str
    label: str
    group: str


SG_TRAITS = (
    Trait("age", "年龄", "基本属性"),
    Trait("education", "学历", "基本属性"),
    Trait("domestic_scope", "国内范围", "地域属性"),
    Trait("family_finance", "家庭经济状况", "社会属性"),
    Trait("further_study", "升学需求", "社会属性"),
    Trait("employment", "就业需求", "社会属性"),
    Trait("admission", "入学能力", "社会属性"),
    Trait("overseas_intent", "留学意愿", "其他属性"),
    Trait("policy_attention", "政策关注度", "其他属性"),
)
DE_TRAITS = (
    Trait("age", "年龄", "基本属性"),
    Trait("education", "学历", "基本属性"),
    Trait("employment", "就业导向", "社会属性"),
    Trait("further_study", "升学需求", "社会属性"),
    Trait("immigration", "移民需求", "社会属性"),
    Trait("skill", "技能需求", "社会属性"),
    Trait("german", "语言能力", "社会属性"),
    Trait("family_support", "家庭支持", "社会属性"),
    Trait("cost_sense", "经济理性", "社会属性"),
    Trait("overseas_intent", "留学意愿", "其他属性"),
    Trait("policy_attention", "政策关注度", "其他属性"),
    Trait("learning_attitude", "学习态度", "其他属性"),
)
PORTRAIT_KEYS = (
    "domestic_scope", "family_finance", "further_study", "employment", "admission",
    "overseas_intent", "policy_attention", "immigration", "skill", "german",
    "family_support", "cost_sense", "learning_attitude",
    "gender", "core_demand", "language_ability", "hands_on", "logical_thinking",
)
PORTRAIT_LABELS = {
    "国内范围": "domestic_scope", "地域": "domestic_scope", "所在地": "domestic_scope",
    "家庭经济状况": "family_finance", "家庭收入": "family_finance",
    "升学需求": "further_study",
    "就业需求": "employment", "就业导向": "employment",
    "入学能力": "admission",
    "留学意愿": "overseas_intent",
    "政策关注度": "policy_attention",
    "移民需求": "immigration",
    "技能需求": "skill",
    "语言能力": "language_ability", "德语水平": "german",
    "家庭支持": "family_support",
    "经济理性": "cost_sense",
    "学习态度": "learning_attitude",
    "性别": "gender", "核心需求": "core_demand", "动手能力": "hands_on", "逻辑思维": "logical_thinking",
}
IMPORT_TRAIT_KEYS = {
    **PORTRAIT_LABELS, **{key: key for key in PORTRAIT_KEYS},
    "location": "domestic_scope", "地区": "domestic_scope", "城市": "domestic_scope",
    "annual_income_range": "family_finance", "家庭年收入": "family_finance", "年收入": "family_finance",
    "language_ability": "language_ability", "语言能力": "language_ability",
}
_HINTS = (
    ("family_finance", ("家庭收入", "家庭经济", "中等收入", "收入一般")),
    ("further_study", ("升学需求", "想升学", "想读本科", "想读硕士", "专升本", "本升硕")),
    ("employment", ("就业需求", "就业导向", "想就业", "找工作", "保就业")),
    ("admission", ("入学测试", "英语口语", "英语笔试", "心理测评")),
    ("overseas_intent", ("想留学", "出国留学", "愿意出国", "不想留学", "不想出国")),
    ("policy_attention", ("一带一路", "乡村振兴")),
    ("immigration", ("想移民", "移民需求", "永居")),
    ("skill", ("动手能力", "逻辑思维", "实践能力")),
    ("german", ("德语",)),
    ("family_support", ("家里支持", "父母支持", "家庭支持")),
    ("cost_sense", ("免学费", "在意费用", "学费", "贷款")),
    ("learning_attitude", ("封闭实训", "封闭式", "愿意参加培训")),
    ("domestic_scope", ("户籍", "所在地")),
)
_LEVEL = re.compile(r"德语\s*(?:水平|等级|证书)?\s*[:：]?\s*(?P<level>[ABC][12])\b", re.I)
_UNCERTAIN = re.compile(r"没有|还没|尚未|未过|未通过|未达到|不是|计划|想考|备考|目标|要求|学习中|培训|课程|如果")
_LANGUAGE_SPLIT = re.compile(r"[；;\r\n]+")


def combined_language_ability(value: str | None, legacy_german: str | None = None) -> str:
    entries = [item.strip() for item in _LANGUAGE_SPLIT.split(value or "") if item.strip()]
    for item in _LANGUAGE_SPLIT.split(legacy_german or ""):
        item = item.strip()
        if item and item not in entries:
            label = item if "德语" in item else f"德语：{item}"
            if label not in entries:
                entries.append(label)
    return "；".join(dict.fromkeys(entries))


def traits_for(project: str | None) -> tuple[Trait, ...]:
    if project == "de_vocational":
        return DE_TRAITS
    if project and project.startswith("sg_"):
        return SG_TRAITS
    return ()


def extract_portrait(record: dict, text: str) -> dict[str, str]:
    """只保留能对上规则属性的内容，不把整份资料原文写进画像。"""
    found = {}
    for key in PORTRAIT_KEYS:
        raw = record.get(key)
        if isinstance(raw, str) and raw.strip():
            found[key] = raw.strip()[:1000 if key == "language_ability" else 128]
    for key, hints in (("hands_on", ("动手能力",)), ("logical_thinking", ("逻辑思维",))):
        if key not in found and (part := _sentence(text, hints)):
            found[key] = part[:128]
    if "skill" not in found:
        skill = "；".join(dict.fromkeys(found[key] for key in ("hands_on", "logical_thinking") if key in found))
        if skill:
            found["skill"] = skill[:128]
    for key, words in _HINTS:
        if key in found:
            continue
        sentence = _sentence(text or "", words)
        if sentence:
            found[key] = sentence[:128]
    language = combined_language_ability(found.get("language_ability"), found.pop("german", None))
    if language:
        found["language_ability"] = language[:1000]
    return found


def merge_observations(current: dict, metadata: dict, updates: dict, source: str, timestamp: str, *, confirmed: bool = False):
    """合并同一人的事实，未经确认的来源不能覆盖现值。"""
    accepted = {}
    evidence = dict(metadata)
    for key, value in updates.items():
        previous = dict(evidence.get(key) or {})
        old_value = current.get(key)
        entry = {"source": source, "updated_at": timestamp, "confirmed": confirmed}
        if not confirmed and (old_value not in (None, "") or previous.get("confirmed")):
            if old_value != value:
                conflicts = list(previous.get("conflicts", []))
                candidate = {"value": value, "source": source}
                if not any(all(item.get(k) == v for k, v in candidate.items()) for item in conflicts):
                    previous["conflicts"] = [*conflicts[-4:], {**candidate, "updated_at": timestamp}]
                    evidence[key] = previous
            continue
        if old_value == value and previous.get("confirmed") == confirmed and not previous.get("conflicts"):
            continue
        if old_value != value:
            accepted[key] = value
        evidence[key] = entry
    return accepted, evidence


def portrait_findings(project: str | None, values: dict[str, str]) -> tuple[str, ...]:
    traits = traits_for(project)
    if not traits:
        return ()
    filled = []
    missing = []
    language = "；".join(
        item for item in _LANGUAGE_SPLIT.split(combined_language_ability(values.get("language_ability"), values.get("german")))
        if "德语" in item
    )
    for trait in traits:
        text = language if trait.key == "german" else (values.get(trait.key) or "").strip()
        if text:
            filled.append(f"{trait.label}：{text}")
        elif trait.key not in ("age", "education"):
            missing.append(trait.label)
    notes = []
    if filled:
        notes.append("画像已记录" + "；".join(filled) + "。")
    if missing:
        notes.append("画像还没有这些属性：" + "、".join(missing) + "。")
    if project == "de_vocational" and language:
        levels = [match["level"].upper() for match in _LEVEL.finditer(language)]
        reached = bool(levels) and all(level in {"B1", "B2", "C1", "C2"} for level in levels) and not _UNCERTAIN.search(language)
        notes.append(
            "画像申报达到德语 B1 或以上，匹配企业前需核对语言证明。"
            if reached else "规则要求匹配德国企业前达到德语 B1，当前语言能力还需要继续确认。"
        )
    intent = values.get("overseas_intent") or ""
    if "不想" in intent or "没有留学" in intent:
        notes.append("画像里的留学意愿偏低，请顾问确认是否还有其他项目可以推进。")
    return tuple(notes)


_EDUCATION_LEVELS = (
    ("博士", "postgraduate"), ("硕士", "postgraduate"), ("本科", "bachelor"),
    ("大专", "college"), ("专科", "college"), ("职高", "vocational_secondary"),
    ("中专", "vocational_secondary"), ("中职", "vocational_secondary"), ("技校", "vocational_secondary"),
    ("高中", "senior_secondary"), ("初中", "junior_secondary"),
)
_STAGE_LEVELS = (("已毕业", "graduated"), ("高二", "senior_year_two"), ("在读", "enrolled"), ("毕业", "graduated"))
_NAME = re.compile(r"(?:我叫|我的名字是|叫我)\s*([A-Za-z\u4e00-\u9fff·]{2,12})")
_NAME_STOP = {"什么", "什么吗", "啥", "啥吗", "谁", "哪个", "名字", "姓名", "学生", "同学"}
_ASKS_IDENTITY = re.compile(r"我是谁|我叫什么|我叫啥|我的名字[是叫]?什么|我的姓名[是叫]?什么|记得我")
_THIRD_PARTY = re.compile(r"我(?:的)?(?:妹妹|姐姐|弟弟|哥哥|孩子|女儿|儿子|家人|同学|朋友|同事|学生)|替别人|帮别人|(?:^|[，。；\s])[他她](?:是|想|叫|今|\d)")
_HYPOTHETICAL = re.compile(r"如果|假设|假如|举例|比如|假定")
_PROFILE_QUESTION = re.compile(r"多少钱|是否需要|需要多少|有什么|能不能|要不要|哪里|怎么|什么条件|是不是")


def person_updates(text: str) -> dict:
    """只接受明确的本人陈述，含糊的咨询和例子留在对话上下文。"""
    if not text or _THIRD_PARTY.search(text) or _HYPOTHETICAL.search(text):
        return {}
    found = {}
    for sentence in re.split(r"[。！？?!；;\n]", text):
        sentence = sentence.strip()
        if not sentence.startswith(("我", "本人")) or sentence.endswith(("吗", "么", "如何", "怎么办")):
            continue
        for clause in re.split(r"[，,]", sentence):
            clause = clause.strip()
            if not clause:
                continue
            age = re.fullmatch(r"(?:我|本人)?(?:今年|现在|年龄(?:是|为)?|已满)?\s*(\d{1,3})\s*岁", clause)
            if age and int(age[1]) <= 120 and not _UNCERTAIN.search(clause):
                found["age"] = int(age[1])
            education = next((code for word, code in _EDUCATION_LEVELS if word in clause), None)
            assertion = re.fullmatch(r"(?:我|本人)?(?:现在|目前|已经)?(?:是|只有|读|就读|正在读|学历(?:是|为)?)?\s*(?:博士|硕士|本科|大专|专科|职高|中专|中职|技校|高中|初中)(?:学历|已毕业|毕业|在读|高二在读)?", clause)
            if education and assertion:
                found["education_level"] = education
                stage = next((code for word, code in _STAGE_LEVELS if word in clause), None)
                if stage:
                    found["education_stage"] = stage
            language = ""
            if not clause.endswith(("吗", "么", "如何")) and not _PROFILE_QUESTION.search(clause):
                extracted = extract_portrait({}, clause)
                language = extracted.pop("language_ability", "")
                found.update(extracted)
            gender = re.fullmatch(r"(?:我|本人)?(?:性别(?:是|为)?|是)(男|女)(?:生|性)?", clause)
            if gender:
                found["gender"] = gender[1]
            if location := re.fullmatch(r"(?:我|本人)(?:来自|现居|住在)([\u4e00-\u9fff]{2,16})", clause):
                found["domestic_scope"] = location[1]
            if re.fullmatch(r"(?:我|本人)?(?:已考|考了|目前)?(?:雅思|托福)\s*\d{1,3}(?:\.\d+)?\s*分?", clause):
                language = clause.removeprefix("我").removeprefix("本人")
            if language:
                found["language_ability"] = combined_language_ability(
                    "；".join(filter(None, (found.get("language_ability"), language))),
                )[:1000]
            if re.search(r"(?:想去|想了解|打算去|考虑去|希望去)(?:新加坡|德国)", clause):
                places = [country for country in ("新加坡", "德国") if _wants(clause, country)]
                if places:
                    found.setdefault("overseas_intent", "关注" + "、".join(places))
    return found


def stated_name(text: str) -> str:
    if not text or _ASKS_IDENTITY.search(text) or _THIRD_PARTY.search(text) or _HYPOTHETICAL.search(text):
        return ""
    found = _NAME.search(text or "")
    if not found:
        return ""
    if re.search(r"[？?]|(?:是|叫).*吗", text.split("，", 1)[0]):
        return ""
    name = found.group(1).strip("，,。的吗呢啊呀")
    if not name or name in _NAME_STOP or name.startswith(("什么", "啥", "谁", "哪")):
        return ""
    return name


def _wants(text: str, word: str) -> bool:
    return word in text and re.search(rf"不[想去考虑要]{{0,3}}{word}", text) is None


def _sentence(text: str, words: tuple[str, ...]) -> str:
    for part in re.split(r"[。！？；;\n]", text):
        if not any(word in part for word in words):
            continue
        if re.search(r"意向项目|目标项目", part) and not any(word in part for word in ("需求", "愿意", "想", "德语")):
            continue
        cleaned = part.strip(" ，,;；:：")
        if cleaned:
            return cleaned
    return ""


RULE_VERSION = "sg-4-9_de-3-12_v1"


def screening_document(subject_id: str, fields: dict, attributes: dict, *, project_label: str | None) -> list[dict]:
    """同一份 JSON 用于页面预览、历史快照和 Dify 输入。"""
    def value(key):
        return attributes.get(key) or None

    shared_attributes = {
        key: value(key)
        for key in PORTRAIT_KEYS
        if key not in {"gender", "domestic_scope", "family_finance", "core_demand", "language_ability", "german"}
    }
    labels = {key: label for label, key in reversed(PORTRAIT_LABELS.items())}
    known_traits = {labels[key]: item for key, item in shared_attributes.items() if item}
    return [{
        "id": subject_id,
        "name": fields.get("customer_name") or None,
        "age": fields.get("age"),
        "gender": fields.get("gender"),
        "education": value("education"),
        "location": value("domestic_scope"),
        "annual_income_range": value("family_finance"),
        "core_demand": fields.get("core_demand") or "；".join(dict.fromkeys(
            value(key) for key in ("further_study", "employment", "immigration") if value(key)
        )) or None,
        "language_ability": combined_language_ability(value("language_ability"), value("german")) or None,
        "target_project": project_label,
        "profile_summary": "；".join(f"{label}：{item}" for label, item in known_traits.items()) or None,
        "tag_weight": fields.get("tag_weight") or {},
        "education_stage": fields.get("education_stage"),
        "intended_major": fields.get("intended_major"),
        "rule_attributes": shared_attributes,
    }]
