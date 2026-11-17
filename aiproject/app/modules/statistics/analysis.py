from datetime import date, timedelta
import json

from fastapi.encoders import jsonable_encoder

from . import analysis_repository as repo, board_service, wellbeing
from .service import _report_department


def customer_analysis(db, principal, start, end):
    current = board_service.operations(db, principal, "customers", start, end)
    comparisons = {}
    count = sum(current["leads_by_status"].values())
    for key, (first, last) in board_service._complaint_comparison_periods(start, end).items():
        prior = board_service.operations(db, principal, "customers", first, last)
        baseline = sum(prior["leads_by_status"].values())
        comparisons[key] = {"start": first, "end": last, "count": baseline,
                            "change": count - baseline,
                            "percent": round((count - baseline) / baseline * 100, 1) if baseline else None}
    return {"comparisons": comparisons, "groups": repo.customer_groups(
        db, _report_department(db, principal), start, end)}


def complaint_analysis(db, principal, start, end):
    from .rules import read_rules
    board_service.operations(db, principal, "complaints", start, end)
    times = repo.complaint_timings(db, _report_department(db, principal), start, end)
    first_response, resolution = {}, {}
    for ticket_id, created, action_at, details in times:
        try:
            status = json.loads(details).get("status")
        except (ValueError, TypeError):
            continue
        elapsed = (action_at + timedelta(hours=8) - created).total_seconds() / 3600
        if elapsed < 0:
            continue
        if status == "processing":
            first_response.setdefault(ticket_id, elapsed)
        if status == "resolved":
            resolution.setdefault(ticket_id, elapsed)
    def metric(values):
        return {"samples": len(values), "average_hours": round(sum(values.values()) / len(values), 2) if values else None}
    days = read_rules(db)["settings"]["complaint_overdue_days"]
    late = sum(value > days * 24 for value in resolution.values()) if days else None
    return {"first_response": metric(first_response), "resolution": metric(resolution),
            "overdue_days": days, "late_resolutions": late,
            "resolution_overdue_percent": round(late / len(resolution)*100, 1) if days and resolution else None,
            "note": "按所选期间创建的投诉及已记录的状态审计计算。旧工单无审计时不计入耗时样本。"}


def wellbeing_trend(db, principal, anchor):
    population = wellbeing.weekly_student_ids(db, principal)
    monday, _ = wellbeing.week_bounds(anchor)
    if (monday - date.min).days < 49:
        from app.core.exceptions import BusinessError
        raise BusinessError(422, "请选择可计算前八周的日期")
    rows = []
    for offset in range(7, -1, -1):
        stats = wellbeing.week_statistics(db, monday - timedelta(weeks=offset), population)
        rows.append({key: stats[key] for key in (
            "period_start", "period_end", "eligible", "participants", "suppressed", "items",
            "emotion", "stress", "emotion_tags", "emotion_scores")})
    return jsonable_encoder({"weeks": rows})

def customer_intelligence(db, principal, start, end):
    from collections import Counter
    from .rules import read_rules
    from .periods import beijing_now
    board_service.operations(db, principal, "customers", start, end)
    scope = _report_department(db, principal)
    rows, events = repo.customer_features(db, scope, start, end)
    policy = read_rules(db)["settings"]
    now = beijing_now()
    vectors = []
    for row in rows:
        age, score = row["age"], row["match_score"]
        if age is None or score is None or not (0 <= age <= 120 and 0 <= score <= 100):
            continue
        inactive = max(0, (now - (row["last_contact_time"] or row["create_time"])).days)
        vectors.append((age / 120, float(score) / 100, min(inactive, 365) / 365))
    clusters = []
    if vectors:
        ordered = sorted(set(vectors))
        k = min(3, len(ordered))
        centers = [ordered[(len(ordered) - 1) * i // max(1, k - 1)] for i in range(k)]
        for _ in range(50):
            groups = [[] for _ in centers]
            for point in vectors:
                nearest = min(range(k), key=lambda i: sum((a-b)**2 for a,b in zip(point, centers[i])))
                groups[nearest].append(point)
            updated = [tuple(sum(p[j] for p in group) / len(group) for j in range(3)) if group else centers[i]
                       for i, group in enumerate(groups)]
            if updated == centers:
                break
            centers = updated
        clusters = [{"group": i+1, "count": len(group), "average_age": round(center[0]*120, 1),
                     "average_match_score": round(center[1]*100, 1), "average_inactive_days": round(center[2]*365, 1)}
                    for i, (group, center) in enumerate(zip(groups, centers)) if group]
    paths = {}
    for lead_id, status in events:
        paths.setdefault(lead_id, []).append(status)
    counts = Counter(" → ".join(path) for path in paths.values())
    threshold = policy["high_value_match_score"]
    high_value = [row for row in rows if threshold is not None and row["match_score"] is not None
                  and row["match_score"] >= threshold and row["status"] != "lost"]
    cutoff = policy["lead_inactive_days"]
    stale = repo.stale_customers(db, scope, now-timedelta(days=cutoff)) if cutoff else []
    return {
        "clusters": clusters, "cluster_samples": len(vectors), "cluster_excluded": len(rows)-len(vectors),
        "cluster_method": "年龄、研判匹配度、距最后联系天数标准化后的确定性 K-means 分群；缺少年龄或匹配度的记录不参与。",
        "paths": [{"path": path, "count": count} for path, count in counts.most_common()],
        "unrecorded_paths": len(rows)-len(paths),
        "high_value": {"threshold": threshold, "count": len(high_value),
                       "countries": dict(Counter(row["intended_country"] or "未填写" for row in high_value)),
                       "education": dict(Counter(row["education_level"] or "未填写" for row in high_value))},
        "inactive": {"days": cutoff, "count": len(stale),
                     "items": [{"id": row["id"], "days": (now-(row["last_contact_time"] or row["create_time"])).days}
                               for row in stale[:100]]},
    }


def project_health(db, principal):
    from .service import current_report_members
    from .rules import read_rules
    from .periods import beijing_now
    members = current_report_members(db, principal)
    population = repo.project_population(db, members)
    projects = {}
    for project, student in population:
        projects.setdefault(project, set()).add(student)
    issues = repo.project_issues(db, {student for students in projects.values() for student in students}, beijing_now())
    policy = read_rules(db)["settings"]
    weights = [policy[key] for key in ("project_complaint_weight", "project_application_weight", "project_deadline_weight")]
    names = repo.project_names(db, projects)
    rows = []
    for project, students in projects.items():
        counts = [len(students.intersection(group)) for group in issues]
        score = None if any(value is None for value in weights) else round(
            100 * (1 - sum(weight * count / len(students) for weight,count in zip(weights,counts))), 1)
        rows.append({"project_id": project, "project_name": names.get(project, "项目 "+str(project)),
                     "students": len(students), "open_complaints": counts[0],
                     "overdue_applications": counts[1], "overdue_deadlines": counts[2], "score": score})
    return {"items": rows, "weights": weights, "note": "按当前负责老师所属组织的班级统计。配置权重后按各类问题涉及学生比例计算，100 分表示当前无这三类未完成事项。"}


def customer_summary(db, principal, start, end):
    from . import report_ai
    from .periods import beijing_now
    stats = board_service.operations(db, principal, "customers", start, end)
    insights = customer_analysis(db, principal, start, end)
    stats.pop("items", None)
    stats.pop("has_more", None)
    db.rollback()
    summary = report_ai.customer_summary(jsonable_encoder({**stats, **insights}))
    # Recheck scope and statistics after the model call.
    current = board_service.operations(db, principal, "customers", start, end)
    current.pop("items", None)
    current.pop("has_more", None)
    if current != stats or customer_analysis(db, principal, start, end) != insights:
        from app.core.exceptions import BusinessError
        raise BusinessError(409, "客户统计已变化，请刷新后重新生成")
    return {"summary": summary, "generated_at": beijing_now()}

def classify_complaint(db, staff, ticket_id):
    from app.core.security.authorization import require_permission
    from app.core.exceptions import BusinessError
    from app.modules.feedback.repository import FeedbackRepository
    from . import report_ai
    require_permission(staff, "tickets:route")
    if staff.role_code not in ("admin", "manager"):
        raise BusinessError(403, "仅管理员或主管可以核验投诉分类")
    row = FeedbackRepository(db).get(ticket_id)
    if row is None or row["ticket_type"] != "complaint":
        raise BusinessError(404, "投诉不存在")
    content = row["content"]
    db.rollback()
    category = report_ai.classify_complaint(content)
    current = FeedbackRepository(db).get(ticket_id)
    if current is None or current["content"] != content:
        raise BusinessError(409, "投诉内容已变化，请刷新后重试")
    return {"category": category, "requires_review": True}
