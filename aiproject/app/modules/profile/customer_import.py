import json
import re
import unicodedata

from pydantic import ValidationError

from app.core.exceptions import BusinessError
from app.modules.consultant.customer_schemas import SharedFields
from app.modules.profile.schemas import Education, EducationStage, Project

from .extract import extract_text
from .portrait import IMPORT_TRAIT_KEYS, extract_portrait


PROJECT_LABELS = {
    Project.SG_JUNIOR: "新加坡初中升学", Project.SG_SENIOR: "新加坡高中或同等学历升学",
    Project.SG_HOSPITALITY: "新加坡酒店就业班", Project.SG_AVIATION: "新加坡航空就业班",
    Project.SG_TOP_UP: "新加坡专升本", Project.SG_MASTERS: "新加坡本升硕", Project.DE_VOCATIONAL: "德国双元制",
}
EDUCATION_LABELS = {
    Education.JUNIOR: "初中", Education.SENIOR: "高中", Education.VOCATIONAL: "中职或同等学历",
    Education.COLLEGE: "大专", Education.BACHELOR: "本科", Education.POSTGRADUATE: "研究生",
    Education.OTHER: "其他",
}
STAGE_LABELS = {
    EducationStage.ENROLLED: "在读", EducationStage.SENIOR_YEAR_TWO: "高二在读",
    EducationStage.GRADUATED: "已毕业",
}

_ALIASES = {
    "姓名": "name", "客户姓名": "name", "本人姓名": "name",
    "本人手机号": "mobile", "登录手机号": "mobile", "手机号": "mobile", "手机号码": "mobile",
    "昵称": "nickname", "联系方式": "contact_info", "年龄": "age",
    "学历": "education", "学历类别": "education", "在读或毕业状态": "education_stage",
    "毕业状态": "education_stage", "意向项目": "target_project", "目标项目": "target_project",
    "意向专业": "intended_major",
    **IMPORT_TRAIT_KEYS,
    "核心需求": "core_demand",
    "需求": "core_demand",
    "核心诉求": "core_demand",
    "德语水平": "german",
    "标签权重": "tag_weight",
}
_LABEL_PATTERN = re.compile(
    r"(?:^|[\n;；,，\t ]+)\s*(" + "|".join(sorted(map(re.escape, _ALIASES), key=len, reverse=True))
    + r")\s*[:：]\s*"
)
_MULTIPLE_CUSTOMERS = "文件包含多位客户或身份信息冲突"


def normalized_name(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def normalized_phone(value: str) -> str:
    phone = re.sub(r"[\s-]+", "", unicodedata.normalize("NFKC", value))
    return phone[3:] if phone.startswith("+86") else phone


def normalized_choice(value, labels):
    if value in labels:
        return value
    canonical = str(value or "").strip()
    return next((key for key, label in labels.items() if label == canonical), None)


def _labeled_fields(content: str) -> dict:
    fields = {}
    labels = list(_LABEL_PATTERN.finditer(content))
    for index, match in enumerate(labels):
        end = labels[index + 1].start() if index + 1 < len(labels) else len(content)
        value = content[match.end():end].splitlines()[0].strip(" ,;，；") if content[match.end():end].strip() else ""
        key = _ALIASES[match[1]]
        if key in ("name", "mobile") and key in fields:
            raise BusinessError(422, _MULTIPLE_CUSTOMERS)
        if value:
            fields[key] = value
    return fields


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        field = _ALIASES.get(key, key)
        if field in result and field in ("name", "mobile"):
            raise BusinessError(422, _MULTIPLE_CUSTOMERS)
        result[field] = value
    return result


def _sample_education(value: str) -> tuple[Education | None, EducationStage | None]:
    value = value.strip()
    if re.search(r"不是|没有|想读|计划|假设|如果", value):
        return None, None
    education = normalized_choice(value, EDUCATION_LABELS)
    if education is None:
        levels = (
            (r"研究生|硕士|博士", Education.POSTGRADUATE),
            (r"本科", Education.BACHELOR),
            (r"大专|专科", Education.COLLEGE),
            (r"中职|中专|职高|技校|中技", Education.VOCATIONAL),
            (r"高中|高二|高三", Education.SENIOR),
            (r"初中|初三", Education.JUNIOR),
        )
        education = next((level for pattern, level in levels if re.search(pattern, value)), None)
    stage = None
    if "毕业" in value and "未毕业" not in value:
        stage = EducationStage.GRADUATED
    elif "高二" in value:
        stage = EducationStage.SENIOR_YEAR_TWO
    elif "在读" in value or re.search(r"大[一二三四]", value):
        stage = EducationStage.ENROLLED
    return education, stage


def read_import(file_name: str, content: bytes) -> tuple[str, str, str, dict]:
    text = extract_text(file_name, content, preserve_pdf_pages=True).strip()
    if not text or len(text.encode("utf-8")) > 60000:
        raise BusinessError(422, "无法读取有效正文，或文件正文过长")
    try:
        record = json.loads(text, object_pairs_hook=_unique_fields)
    except json.JSONDecodeError:
        records = [_labeled_fields(page) for page in text.split("\f")]
        candidates = [r for r in records if r.get("name") or r.get("mobile")]
        if len(candidates) > 1:
            raise BusinessError(422, _MULTIPLE_CUSTOMERS)
        record = candidates[0] if candidates else {}
    if isinstance(record, list):
        if len(record) != 1:
            raise BusinessError(422, _MULTIPLE_CUSTOMERS)
        record = record[0]
    if not isinstance(record, dict):
        raise BusinessError(422, "无法读取客户资料字段")
    record = {_ALIASES.get(k, k): v for k, v in record.items()}
    name = normalized_name(str(record.get("name") or ""))
    mobile = normalized_phone(str(record.get("mobile") or ""))
    if not name or not re.fullmatch(r"1[3-9][0-9]{9}", mobile):
        raise BusinessError(422, "无法确认资料归属，正文需要同时包含本人姓名和手机号")
    fields = {}
    for field, raw in (("nickname", record.get("nickname")), ("contact_info", record.get("contact_info")),
                       ("intended_major", record.get("intended_major"))):
        if isinstance(raw, str) and raw.strip():
            fields[field] = raw
    for field, raw, labels in (
        ("education_level", record.get("education"), EDUCATION_LABELS),
        ("education_stage", record.get("education_stage"), STAGE_LABELS),
        ("intended_project", record.get("target_project"), PROJECT_LABELS),
    ):
        value = normalized_choice(raw, labels) if isinstance(raw, str) else None
        if value is not None:
            fields[field] = value
    raw_education = record.get("education")
    if isinstance(raw_education, str):
        education, stage = _sample_education(raw_education)
        if education:
            fields.setdefault("education_level", education)
        if stage:
            fields.setdefault("education_stage", stage)
    target = record.get("target_project")
    if "intended_project" not in fields and isinstance(target, str):
        patterns = (
            ("中德|德国|双元制", Project.DE_VOCATIONAL),
            ("酒店运营|酒店就业", Project.SG_HOSPITALITY),
            ("航空运营|航空就业", Project.SG_AVIATION),
            ("专升本", Project.SG_TOP_UP),
            ("本升硕", Project.SG_MASTERS),
            (r"0\.5|高中升学", Project.SG_SENIOR),
            (r"2\s*\+\s*2|初中升学", Project.SG_JUNIOR),
        )
        project = next((item for pattern, item in patterns if re.search(pattern, target)), None)
        if project:
            fields["intended_project"] = project
    tags = record.get("tag_weight")
    if isinstance(tags, dict):
        fields["tag_weight"] = tags
    age = re.fullmatch(r"([0-9]{1,3})\s*岁?", str(record.get("age", "")).strip())
    if age and int(age[1]) <= 120:
        fields["age"] = int(age[1])
    # Only use extracted values for structured documents. Raw JSON can contain
    # identity data and should never be copied into an individual attribute.
    demand = record.get("core_demand")
    if isinstance(demand, str):
        for key, words in (
            ("further_study", ("升学", "学历提升", "深造")),
            ("employment", ("就业", "求职", "找工作")),
            ("immigration", ("移民", "永居")),
        ):
            if any(word in demand for word in words):
                record.setdefault(key, demand)
    summary = record.get("profile_summary")
    fields.update(extract_portrait(record, summary if isinstance(summary, str) else ""))
    try:
        return text, name, mobile, SharedFields.model_validate(fields).model_dump(exclude_unset=True, mode="json")
    except ValidationError:
        raise BusinessError(422, "文件中的资料字段格式有误，请核对后重新上传") from None
