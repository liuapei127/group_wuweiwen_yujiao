"""Student-facing facts from current owned records, separate from conversational memory."""
from . import assistant_workspace_repository as repository, service

STAGES = {"document_prep": "材料准备", "submitted": "已提交", "under_review": "审核中",
          "offer_received": "已获录取", "visa_processing": "签证办理", "enrolled": "已入学"}


def snapshot(db, student_id):
    profile = service.academic_profile(db, student_id)
    progress = []
    for row, handler in repository.applications(db, student_id):
        progress.append({"id": row.id, "school": row.target_school, "major": row.target_major,
                         "stage": row.stage, "stage_label": STAGES.get(row.stage, row.stage),
                         "detail": row.progress_detail, "next_action": row.next_action,
                         "deadline": row.deadline.isoformat() if row.deadline else None,
                         "updated_at": row.update_time.isoformat(), "handler": handler,
                         "source": "员工维护的院校申请记录"})
    deadlines = service.academic_deadlines(db, student_id, offset=0, limit=5, upcoming=True)
    return {"profile": profile, "applications": progress,
            "deadlines": [r.model_dump(mode="json") for r in deadlines.items],
            "position": {"known": False, "description": "没有实时定位；学籍去向不代表实际所在地"},
            "service_stage": {"known": False, "description": "整体服务阶段尚未接入；下列仅为已登记的院校申请进度"},
            "notes": "聊天自述与记忆不是员工核实的学籍或申请状态。"}


def progress_result(context, query=""):
    rows = context["applications"]
    matched = [row for row in rows if row["school"] and row["school"] in query]
    if matched:
        rows = matched
    if not rows:
        answer = "目前没有员工登记的院校申请进度。请联系负责申请的老师或顾问补充；我不能据此判断你已经出国或入学。"
    elif len(rows) == 1:
        row = rows[0]
        answer = f"{row['school']}的申请目前是「{row['stage_label']}」。"
        if row["next_action"]:
            answer += f"下一步：{row['next_action']}。"
        answer += f"记录更新于{row['updated_at'][:16].replace('T', ' ')}（北京时间）。"
    else:
        answer = f"查到{len(rows)}项院校申请，分别列在下面。它们可能处于不同阶段，请按院校查看；不能把其中一项当成你的全部进度。"
    return {"reply": answer, "intent": "progress", "cards": [
        {"title": row["school"], "fields": [
            {"label": "专业", "value": row["major"] or "未登记"},
            {"label": "阶段", "value": row["stage_label"]},
            {"label": "进度说明", "value": row["detail"] or "未补充"},
            {"label": "下一步", "value": row["next_action"] or "请向负责人确认"},
            {"label": "负责人", "value": row["handler"] or "未登记"},
            {"label": "更新时间（北京时间）", "value": row["updated_at"][:16].replace("T", " ")},
            {"label": "来源", "value": row["source"]},
        ]} for row in rows]}
