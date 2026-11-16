"""把上传文件转成可研判的正文。表格里有多位客户时不合并成一份。"""

import csv
import json
from io import BytesIO, StringIO

from app.core.exceptions import BusinessError

_HEADER_KEYS = {
    "id": "id",
    "name": "name",
    "姓名": "name",
    "客户姓名": "name",
    "本人姓名": "name",
    "mobile": "mobile",
    "手机号": "mobile",
    "手机号码": "mobile",
    "登录手机号": "mobile",
    "本人手机号": "mobile",
    "昵称": "nickname",
    "联系方式": "contact_info",
    "在读或毕业状态": "education_stage",
    "毕业状态": "education_stage",
    "意向专业": "intended_major",
    "age": "age",
    "年龄": "age",
    "gender": "gender",
    "性别": "gender",
    "education": "education",
    "学历": "education",
    "location": "location",
    "地区": "location",
    "所在地": "location",
    "城市": "location",
    "annual_income_range": "annual_income_range",
    "年收入": "annual_income_range",
    "家庭年收入": "annual_income_range",
    "收入": "annual_income_range",
    "core_demand": "core_demand",
    "核心需求": "core_demand",
    "需求": "core_demand",
    "language_ability": "language_ability",
    "语言能力": "language_ability",
    "语言": "language_ability",
    "target_project": "target_project",
    "目标项目": "target_project",
    "意向项目": "target_project",
    "profile_summary": "profile_summary",
    "简介": "profile_summary",
    "画像摘要": "profile_summary",
    "tag_weight": "tag_weight",
    "标签": "tag_weight",
}


def extract_text(file_name: str, file_bytes: bytes, *, preserve_pdf_pages: bool = False) -> str:
    """按扩展名抽出文本。空文件返回空字符串。"""
    if not file_bytes:
        return ""
    suffix = file_name.rsplit(".", 1)[-1].lower() if "." in file_name else ""
    if suffix in {"txt", "csv"}:
        return _from_table(_decode(file_bytes), comma=suffix == "csv") if suffix == "csv" else _decode(file_bytes)
    if suffix == "xlsx":
        return _from_xlsx(file_bytes)
    if suffix == "xls":
        return _from_xls(file_bytes)
    if suffix == "pdf":
        return _from_pdf(file_bytes, separator="\f" if preserve_pdf_pages else "\n")
    raise BusinessError(422, "文件格式无法解析")


def _decode(file_bytes: bytes) -> str:
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    return file_bytes.decode("utf-8", errors="replace")


def _from_table(text: str, *, comma: bool) -> str:
    if not comma:
        return text
    rows = [
        [cell.strip() for cell in row]
        for row in csv.reader(StringIO(text))
    ]
    return _rows_to_text(rows)


def _from_xlsx(file_bytes: bytes) -> str:
    try:
        from openpyxl import load_workbook
    except ImportError as exc:
        raise BusinessError(422, "当前环境无法解析 Excel") from exc
    try:
        workbook = load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
    except Exception as exc:
        raise BusinessError(422, "Excel 文件无法读取") from exc
    rows: list[list[str]] = []
    try:
        for sheet in workbook.worksheets:
            for row in sheet.iter_rows(values_only=True):
                rows.append(["" if cell is None else str(cell).strip() for cell in row])
    finally:
        workbook.close()
    return _rows_to_text(rows)


def _from_xls(file_bytes: bytes) -> str:
    try:
        import xlrd
    except ImportError as exc:
        raise BusinessError(422, "当前环境无法解析旧版 Excel") from exc
    try:
        book = xlrd.open_workbook(file_contents=file_bytes)
    except Exception as exc:
        raise BusinessError(422, "Excel 文件无法读取") from exc
    rows: list[list[str]] = []
    for sheet in book.sheets():
        for index in range(sheet.nrows):
            rows.append([str(cell).strip() for cell in sheet.row_values(index)])
    return _rows_to_text(rows)


def _from_pdf(file_bytes: bytes, *, separator: str) -> str:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise BusinessError(422, "当前环境无法解析 PDF") from exc
    try:
        reader = PdfReader(BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:
        raise BusinessError(422, "PDF 文件无法读取") from exc
    return separator.join(part.strip() for part in pages if part.strip())


def _rows_to_text(rows: list[list[str]]) -> str:
    kept = [row for row in rows if any(cell.strip() for cell in row)]
    if not kept:
        return ""
    header = [_header_key(cell) for cell in kept[0]]
    if header.count("name") > 1 or header.count("mobile") > 1:
        raise BusinessError(422, "文件含多列身份信息，无法确认是同一位客户")
    if sum(key is not None for key in header) >= 2 and len(kept) > 1:
        records = []
        for row in kept[1:]:
            record: dict[str, object] = {}
            for key, value in zip(header, row):
                if key and value.strip():
                    record[key] = _coerce(key, value.strip())
            if record:
                records.append(record)
        if len(records) == 1:
            return json.dumps(records[0], ensure_ascii=False)
        if len(records) > 1:
            return json.dumps(records, ensure_ascii=False)
    return "\n".join(" ".join(cell.strip() for cell in row if cell.strip()) for row in kept)


def _header_key(cell: str) -> str | None:
    text = cell.strip()
    if text in _HEADER_KEYS:
        return _HEADER_KEYS[text]
    lowered = text.lower()
    return _HEADER_KEYS.get(lowered)


def _coerce(key: str, value: str) -> object:
    if key == "age" and value.isdigit():
        return int(value)
    if key == "tag_weight" and value.startswith("{"):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return value
        if isinstance(parsed, dict):
            return parsed
    return value
