from datetime import datetime, time, timedelta

from sqlalchemy import BigInteger, Date, Integer, String, case, column, distinct, func, select, table, or_

from app.modules.student.alerts import _alert

records = table(
    "student_psych_record", column("id", BigInteger), column("student_id", BigInteger),
    column("emotion_tag", String), column("emotion_score", Integer), column("record_date", Date),
)


def weekly_distributions(db, population, consented, start, end, minimum):
    filters = (records.c.student_id.in_(consented), records.c.record_date.between(start, end))
    participants = db.scalar(select(func.count(distinct(records.c.student_id))).where(*filters))
    tags = func.coalesce(func.nullif(func.trim(records.c.emotion_tag), ""), "未标注")
    score = records.c.emotion_score
    buckets = case(
        (score.is_(None), "未评分"), (score < 0, "无效分值"), (score > 100, "无效分值"),
        (score < 20, "0–19"), (score < 40, "20–39"), (score < 60, "40–59"),
        (score < 80, "60–79"), else_="80–100",
    )
    data = {"emotion_tags": [], "emotion_scores": [], "records_suppressed": participants < minimum}
    if participants >= minimum:
        for name, label in (("emotion_tags", tags), ("emotion_scores", buckets)):
            query = select(label, func.count()).where(*filters).group_by(label).having(
                func.count(distinct(records.c.student_id)) >= minimum).order_by(label)
            data[name] = [{"label": label, "count": count} for label, count in db.execute(query)]

    reason = func.coalesce(_alert.c.trigger_reason, "")
    categories = [
        ("学习压力", ("学习", "考试", "成绩", "作业", "学业")),
        ("生活适应", ("适应", "生活", "住宿", "时差", "想家")),
        ("人际关系", ("人际", "同学", "朋友", "关系", "孤独")),
        ("情绪困扰", ("焦虑", "低落", "情绪", "紧张", "失眠")),
    ]
    category = case(
        (func.trim(reason) == "", "未填写"),
        *((reason.contains(word), name) for name, words in categories for word in words),
        else_="其他原因",
    )
    query = select(category, func.count()).where(
        _alert.c.student_id.in_(population),
        _alert.c.create_time >= datetime.combine(start, time.min),
        _alert.c.create_time < datetime.combine(end + timedelta(days=1), time.min),
    ).group_by(category).order_by(category)
    data["alert_reasons"] = [{"label": label, "count": count} for label, count in db.execute(query)]
    data["milestones"] = milestone_correlations(db, consented, start, end, minimum) if participants >= minimum else []
    return data


def milestone_correlations(db, consented, start, end, minimum):
    from sqlalchemy import exists
    from app.modules.student.models import ApplicationProgress, AcademicDeadline
    filters = (records.c.student_id.in_(consented), records.c.record_date.between(start, end))
    application = exists(select(ApplicationProgress.id).where(
        ApplicationProgress.student_id == records.c.student_id, ApplicationProgress.deadline.between(start, end)))
    academic = exists(select(AcademicDeadline.id).where(
        or_(AcademicDeadline.student_id == records.c.student_id, AcademicDeadline.student_id.is_(None)),
        AcademicDeadline.deadline >= datetime.combine(start, time.min),
        AcademicDeadline.deadline < datetime.combine(end+timedelta(days=1), time.min)))
    labels = [
        ("申请或签证截止节点", application),
        ("考务截止节点", academic),
        ("无当周截止节点", ~application & ~academic),
    ]
    result = []
    valid_score = case((records.c.emotion_score.between(0,100), records.c.emotion_score), else_=None)
    for label, condition in labels:
        count, students, average = db.execute(select(func.count(), func.count(distinct(records.c.student_id)),
            func.avg(valid_score)).where(*filters, condition)).one()
        if students >= minimum:
            result.append({"label":label, "records":count, "students":students,
                           "average_score":round(float(average),1) if average is not None else None})
    return result
