from datetime import timedelta

from sqlalchemy import insert, select
from app.modules.student.alerts import _alert
from app.modules.student_admin.repository import StudentAdminRepository
from app.modules.todo.models import notification_log
from .analysis_models import ReportRuleSignal
from .rules import read_rules
from .periods import beijing_now


def check_student_self_assessment(db, student_id, today):
    from .wellbeing_models import WellbeingCheckin
    config = read_rules(db)
    days = config["settings"]["psych_negative_days"]
    if days is None:
        return False
    expected = today
    streak_start = None
    count = 0
    query = select(WellbeingCheckin).where(
        WellbeingCheckin.student_id == student_id, WellbeingCheckin.day <= today).order_by(WellbeingCheckin.day.desc())
    for row in db.scalars(query):
        if row.day != expected or (row.emotion not in ("poor", "very_poor") and row.stress != "high"):
            break
        streak_start = row.day
        count += 1
        expected -= timedelta(days=1)
    if count < days:
        return False
    key = f"psych:{student_id}:{config['version']}:{streak_start}"
    if db.get(ReportRuleSignal, key):
        return False
    now = beijing_now()
    teacher = StudentAdminRepository(db).class_teacher(student_id)
    result = db.execute(insert(_alert).values(
        student_id=student_id, teacher_id=teacher, risk_level=config["settings"]["psych_alert_level"], status="pending",
        trigger_reason=f"自评规则提示：连续 {count} 天选择低落、很低落或高压力，待班主任人工核验；规则版本 {config['version']}。",
        create_time=now, update_time=now,
    ))
    alert_id = result.lastrowid
    db.add(ReportRuleSignal(key=key, kind="psych_checkin", related_id=alert_id,
                           rule_version=config["version"], created_at=now))
    if teacher:
        db.execute(insert(notification_log).values(
            user_id=teacher, notification_type="psych_alert", title="学生自评需要人工关注",
            content="学生连续自评达到已配置提醒条件，请在心理预警中私下核验。",
            related_type="student_psych_alert", related_id=alert_id, channel="system", status="sent",
            dedup_key=key, create_time=now,
        ))
    return True


def scan_operational_signals(db):
    from sqlalchemy import func
    from app.modules.auth.models import accounts, roles
    from app.modules.auth.repository import AuthRepository
    from app.core.security import EmployeePrincipal
    from app.core.exceptions import BusinessError
    from app.modules.feedback.models import student_feedback_ticket
    from . import analysis_repository, board_repository
    from .service import _report_department
    config = read_rules(db)
    policy = config["settings"]
    if policy["lead_inactive_days"] is None and policy["complaint_overdue_days"] is None:
        return 0
    now = beijing_now()
    managers = db.execute(select(accounts.c.id, accounts.c.role_id).join(
        roles, roles.c.id == accounts.c.role_id).where(
            roles.c.role_code == "manager", roles.c.status == 1, accounts.c.status == "normal",
            accounts.c.user_type == "employee")).all()
    sent = 0
    for manager, role_id in managers:
        permissions = frozenset(AuthRepository(db).permissions(role_id))
        if "reports:operations:read" not in permissions:
            continue
        principal = EmployeePrincipal(manager, permissions, role_code="manager")
        try:
            scope = _report_department(db, principal)
        except BusinessError:
            continue
        if policy["lead_inactive_days"]:
            days = policy["lead_inactive_days"]
            for row in analysis_repository.stale_customers(db, scope, now-timedelta(days=days)):
                age = (now - (row["last_contact_time"] or row["create_time"])).days
                recipients = {row["owner_employee_id"], manager}
                sent += _notify_signal(db, recipients, config["version"], "customer_inactive",
                    row["id"], age-days, policy["reminder_repeat_days"], "客户需要跟进",
                    f"客户编号 {row['id']} 已 {age} 天无联系记录，达到已配置的跟进提醒条件。",
                    "crm_lead", now)
        if policy["complaint_overdue_days"]:
            days = policy["complaint_overdue_days"]
            ticket = student_feedback_ticket.c
            query = select(ticket.id, ticket.assignee_id, ticket.create_time).where(
                ticket.ticket_type == "complaint", ticket.status.in_(("pending", "processing")),
                ticket.create_time <= now-timedelta(days=days))
            for row in db.execute(board_repository.scoped(query, ticket.assignee_id, scope)).mappings():
                age = (now-row["create_time"]).days
                recipients = {row["assignee_id"]} if row["assignee_id"] else set()
                escalate = policy["complaint_escalate_days"]
                if escalate is not None and age >= escalate:
                    recipients.add(manager)
                sent += _notify_signal(db, recipients, config["version"], "complaint_overdue",
                    row["id"], age-days, policy["reminder_repeat_days"], "投诉超时提醒",
                    f"投诉编号 {row['id']} 创建后 {age} 天仍未解决，请核对处理进度。",
                    "student_feedback_ticket", now)
    db.commit()
    return sent


def _notify_signal(db, recipients, version, kind, related_id, age, repeat, title, content, related_type, now):
    from app.modules.auth.models import accounts
    from sqlalchemy.dialects.mysql import insert as mysql_insert
    from sqlalchemy.dialects.sqlite import insert as sqlite_insert
    sent = 0
    valid = db.scalars(select(accounts.c.id).where(
        accounts.c.id.in_(recipients), accounts.c.status == "normal", accounts.c.user_type.in_(("employee","admin"))))
    for user_id in valid:
        bucket = age // repeat if repeat else 0
        key = f"report:{kind}:{related_id}:{user_id}:{version}:{bucket}"
        if db.scalar(select(notification_log.c.id).where(notification_log.c.dedup_key == key)):
            continue
        values = dict(user_id=user_id, notification_type=kind, title=title, content=content,
                      related_type=related_type, related_id=related_id, channel="system", status="sent",
                      dedup_key=key, create_time=now)
        if db.get_bind().dialect.name == "mysql":
            statement = mysql_insert(notification_log).values(**values)
            statement = statement.on_duplicate_key_update(dedup_key=statement.inserted.dedup_key)
        else:
            statement = sqlite_insert(notification_log).values(**values).on_conflict_do_nothing(index_elements=["dedup_key"])
        result = db.execute(statement)
        sent += int(result.rowcount == 1)
    return sent
