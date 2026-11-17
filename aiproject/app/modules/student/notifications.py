from sqlalchemy import insert, select
from sqlalchemy.orm import Session

from app.modules.todo.models import notification_log
from app.shared.utils.time_util import now_naive
from . import repository


def save_student_result(
    db: Session, student_id: int, related_type: str, related_id: int,
    event: str, title: str, content: str, *, notification_type: str = "student_result",
) -> None:
    key = f"student-result:{related_type}:{related_id}:{event}"
    if db.scalar(select(notification_log.c.id).where(notification_log.c.dedup_key == key)) is not None:
        return
    db.execute(insert(notification_log).values(
        user_id=student_id, notification_type=notification_type, dedup_key=key,
        related_type=related_type, related_id=related_id, title=title, content=content,
        channel="system", status="sent", create_time=now_naive(),
    ))


def student_results(db: Session, student_id: int, before_id: int | None, limit: int):
    stmt = select(
        notification_log.c.id, notification_log.c.title, notification_log.c.content,
        notification_log.c.related_type, notification_log.c.related_id, notification_log.c.create_time,
    ).where(
        notification_log.c.user_id == student_id,
        notification_log.c.notification_type.in_(("student_result", "academic_due")),
        notification_log.c.channel == "system", notification_log.c.status == "sent",
    )
    if before_id is not None:
        stmt = stmt.where(notification_log.c.id < before_id)
    notices = [dict(row) for row in db.execute(stmt.order_by(notification_log.c.id.desc()).limit(limit)).mappings()]
    sources = repository.notification_sources(db, student_id, notices)
    for notice in notices:
        source = sources.get((notice["related_type"], notice["related_id"]))
        notice["related_summary"] = None
        notice["related_details"] = None
        if source:
            notice["related_summary"], notice["related_details"] = _source_details(notice["related_type"], source)
    return notices


_STATUS = {"pending": "待处理", "approved": "已通过", "rejected": "已拒绝", "cancelled": "已取消",
           "processing": "处理中", "resolved": "已解决", "closed": "已关闭", "reminded": "待办理",
           "done": "已完成", "missed": "已错过"}


def _when(value) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else "未登记"


def _source_details(source_type: str, row: dict) -> tuple[str, dict]:
    if source_type == "student_admin_service":
        kind = {"sick": "病假", "personal": "事假", "emergency": "紧急事由"}.get(row["leave_type"], "请假")
        span = f"{_when(row['start_time'])} 至 {_when(row['end_time'])}"
        summary = f"{kind} · {span} · {row['reason'][:60]}"
        heading = "请假单详情"
        fields = [("请假单号", str(row["id"])), ("假别", kind), ("起止时间（北京时间）", span),
                  ("请假原因", row["reason"]), ("当前状态", _STATUS.get(row["status"], row["status"])),
                  ("审批意见", row["approval_comment"] or "未填写"), ("审批时间（北京时间）", _when(row["approval_time"]))]
    elif source_type == "student_feedback_ticket":
        summary = row["title"] or row["content"][:80]
        heading = "反馈单详情"
        fields = [("反馈单号", str(row["id"])), ("标题", row["title"] or "未填写标题"),
                  ("类别", {"learning": "学习相关", "company": "公司相关"}.get(row["category"], "其他")),
                  ("提交内容", row["content"]), ("当前状态", _STATUS.get(row["status"], row["status"])),
                  ("处理结果", row["solution"] or "尚未填写"), ("提交时间（北京时间）", _when(row["create_time"]))]
    else:
        summary = f"{row['title']} · 截止 {_when(row['deadline'])}"
        heading = "考务事项详情"
        fields = [("事项", row["title"]), ("说明", row["description"] or "老师尚未补充具体说明，请联系确认"),
                  ("截止时间（北京时间）", _when(row["deadline"])), ("当前状态", _STATUS.get(row["status"], row["status"]))]
    return summary, {"title": heading, "fields": [{"label": label, "value": value} for label, value in fields]}
