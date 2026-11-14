"""Render authorized archive records as downloadable Chinese-language reports."""
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import CondPageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

SECTIONS = (
    ("work_summary", "工作总结"),
    ("key_progress_summary", "关键进展"),
    ("risk_summary", "风险事项"),
    ("next_work_suggestions", "下一步建议"),
)

STATUSES = {
    "new": "新线索", "contacting": "联系中", "qualified": "已确认意向", "signed": "已签约",
    "lost": "已流失", "pending": "待处理", "processing": "处理中", "resolved": "已处理",
    "closed": "已关闭", "following": "跟进中", "dismissed": "已排除",
}
RISKS = {"low": "低", "medium": "中", "high": "高"}


@lru_cache(maxsize=1)
def _font() -> str:
    for path in (Path("C:/Windows/Fonts/simhei.ttf"), Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc")):
        if path.is_file():
            pdfmetrics.registerFont(TTFont("ReportChinese", str(path)))
            return "ReportChinese"
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    return "STSong-Light"


def render_report(report: dict) -> bytes:
    body = report["report_content"]
    font = _font()
    navy = colors.HexColor("#17324D")
    muted = colors.HexColor("#42576E")
    border = colors.HexColor("#D7E0E9")
    text = ParagraphStyle("body", fontName=font, fontSize=10.5, leading=17, textColor=navy, wordWrap="CJK")
    heading = ParagraphStyle("heading", parent=text, fontSize=14, leading=20, spaceBefore=15, spaceAfter=6,
                             keepWithNext=True)
    section_heading = ParagraphStyle("section_heading", parent=heading, keepWithNext=False)
    title = ParagraphStyle("title", parent=text, fontSize=24, leading=32, spaceAfter=7)
    note = ParagraphStyle("note", parent=text, fontSize=10, textColor=muted, spaceAfter=4)

    def para(value, style=text):
        return Paragraph(escape(str(value)).replace(chr(10), "<br/>"), style)

    story = [
        para(report["report_title"], title),
        para(f"统计期间  {report['period_start']} 至 {report['period_end']}", note),
        para("范围  " + (body.get("department") or ("本人负责的学生" if report["report_type"] == "psych_weekly"
                                               else "全公司")), note),
        Spacer(1, 10),
    ]

    def add_table(label, headers, rows):
        story.append(para(label, heading))
        if not rows:
            story.append(para("本期无相关记录"))
            return
        table = Table([[para(value) for value in row] for row in [headers, *rows]],
                      colWidths=[(A4[0] - 108) / len(headers)] * len(headers), repeatRows=1, hAlign="LEFT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF1F7")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FB")]),
            ("LINEBELOW", (0, 0), (-1, 0), 0.7, border),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 10),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(table)

    for key, label in SECTIONS:
        if key in body.get("sections", {}):
            story.extend([CondPageBreak(68), para(label, section_heading), para(body["sections"][key])])
    if "submissions" in body:
        submissions = body["submissions"]
        story.append(para(f"应交 {submissions['expected']} 人 · 已交 {submissions['submitted']} 人 · 未交 {submissions['missing']} 人", note))
        add_table("分部门提交情况", ["部门", "应交", "已交", "未交"], [
            [row["department"] or "未填写部门", row["expected"], row["submitted"], row["missing"]]
            for row in submissions["departments"]
        ])
    if "days" in body:
        add_table(f"日报提交统计 · 累计 {body['submitted_employee_days']} 人次", ["日期", "提交人数"],
                  [[row["report_date"], row["submitted_employees"]] for row in body["days"]])
    for key, label in (("leads_by_status", "客户线索"), ("complaints_by_status", "投诉工单")):
        if key in body:
            add_table(label, ["状态", "数量"], [[STATUSES.get(status, status), count] for status, count in body[key].items()])
    if "items" in body:
        add_table("心理预警汇总", ["状态", "风险等级", "数量"], [
            [STATUSES.get(row["status"], row["status"]), RISKS.get(row["risk_level"], row["risk_level"]), row["count"]]
            for row in body["items"]
        ])

    for key, label in (
        ("transitions", "签约和流失"), ("lost_reasons", "流失原因"), ("categories", "投诉分类"),
        ("backlog", "积压账龄"), ("satisfaction", "满意度"),
    ):
        if key in body:
            add_table(label, ["分类", "数量"], [[STATUSES.get(name, name), count] for name, count in body[key].items()])
    if body.get("as_of"):
        story.append(para(f"积压快照生成时间  {body['as_of']}", note))
    if body.get("status_history_since"):
        story.append(para(f"签约、流失从 {body['status_history_since']} 起开始记录", note))
    if "eligible" in body:
        coverage = "低于展示人数" if body.get("suppressed") else str(body["participants"])
        story.append(para(f"统计范围 {body['eligible']} 人 · 参与自评 {coverage}", heading))
        for key, label in (("emotion", "情绪趋势"), ("stress", "压力趋势")):
            add_table(label, ["日期", "分类", "人数"], [[row["day"], row["label"], row["count"]] for row in body[key]])
    for key, label in (("ai_summary", "AI 摘要"), ("suggestion", "审核建议")):
        if body.get(key):
            story.extend([CondPageBreak(68), para(label, section_heading), para(body[key])])

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setStrokeColor(border)
        canvas.line(48, 45, A4[0] - 48, 45)
        canvas.setFillColor(muted)
        canvas.setFont(font, 9)
        canvas.drawString(48, 29, "粤教教育服务 · 内部报表")
        canvas.drawRightString(A4[0] - 48, 29, f"第 {doc.page} 页")
        canvas.restoreState()

    buffer = BytesIO()
    document = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=48, rightMargin=48,
                                 topMargin=46, bottomMargin=60, title=report["report_title"])
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
