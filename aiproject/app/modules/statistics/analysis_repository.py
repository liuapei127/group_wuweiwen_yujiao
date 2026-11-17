from sqlalchemy import case, func, select, or_

from app.modules.consultant.models import CrmLead
from app.modules.auth.models import audit_log
from app.modules.feedback.models import student_feedback_ticket
from . import board_repository as board


def customer_groups(db, scope, start, end):
    lead = CrmLead
    begin, finish = board.bounds(start, end)
    rows = {}
    for key in ("intended_country", "education_level", "intended_project", "source_channel"):
        field = func.coalesce(func.nullif(func.trim(getattr(lead, key)), ""), "未填写")
        query = select(field, func.count(), func.sum(case((lead.status == "signed", 1), else_=0))).where(
            lead.create_time >= begin, lead.create_time < finish).group_by(field).order_by(func.count().desc())
        rows[key] = [{"label": label, "count": count, "signed": int(signed),
                      "signed_percent": round(int(signed) / count * 100, 1)}
                     for label, count, signed in db.execute(board.scoped(query, lead.owner_employee_id, scope))]
    return rows


def complaint_timings(db, scope, start, end):
    ticket = student_feedback_ticket.c
    begin, finish = board.bounds(start, end)
    query = select(ticket.id, ticket.create_time).where(
        ticket.ticket_type == "complaint", ticket.create_time >= begin, ticket.create_time < finish)
    population = board.scoped(query, ticket.assignee_id, scope).subquery()
    # Audit times are UTC. Business ticket creation times are Beijing local.
    target = func.cast(population.c.id, audit_log.c.target.type)
    if db.get_bind().dialect.name == "mysql":
        target = target.collate("utf8mb4_unicode_ci")
    query = select(population.c.id, population.c.create_time, audit_log.c.create_time, audit_log.c.details).join(
        audit_log, audit_log.c.target == target).where(
            audit_log.c.action == "ticket_processed").order_by(population.c.id, audit_log.c.id)
    return db.execute(query).all()

def customer_features(db, scope, start, end):
    from app.modules.profile.models import CustomerProfile
    from app.modules.consultant.status_events import LeadStatusEvent
    lead, profile = CrmLead, CustomerProfile
    latest = select(profile.lead_id, func.max(profile.id).label("id")).where(
        profile.lead_id.is_not(None)).group_by(profile.lead_id).subquery()
    begin, finish = board.bounds(start, end)
    query = select(lead.id, lead.age, lead.status, lead.intended_country, lead.education_level,
                   lead.last_contact_time, lead.create_time,
                   profile.match_score).outerjoin(latest, latest.c.lead_id == lead.id).outerjoin(
                       profile, profile.id == latest.c.id).where(
                           lead.create_time >= begin, lead.create_time < finish).order_by(lead.id)
    data = db.execute(board.scoped(query, lead.owner_employee_id, scope).limit(5001)).mappings().all()
    if len(data) > 5000:
        from app.core.exceptions import BusinessError
        raise BusinessError(422, "特征分析最多支持 5000 名客户，请缩小日期范围")
    ids = [row["id"] for row in data]
    paths = db.execute(select(LeadStatusEvent.lead_id, LeadStatusEvent.status).where(
        LeadStatusEvent.lead_id.in_(ids)).order_by(
            LeadStatusEvent.lead_id, LeadStatusEvent.occurred_at, LeadStatusEvent.id)).all()
    return data, paths


def stale_customers(db, scope, cutoff):
    lead = CrmLead
    query = select(lead.id, lead.owner_employee_id, lead.last_contact_time, lead.create_time).where(
        lead.status.in_(("new", "contacting", "qualified")),
        func.coalesce(lead.last_contact_time, lead.create_time) <= cutoff)
    return db.execute(board.scoped(query, lead.owner_employee_id, scope)).mappings().all()


def project_population(db, members):
    from app.modules.classroom.models import ClassEnrollment, ProjectClass
    from app.modules.student_admin.models import SysUser
    query = select(ProjectClass.project_id, ClassEnrollment.student_id).join(
        ClassEnrollment, ClassEnrollment.class_id == ProjectClass.id).join(
            SysUser, SysUser.id == ClassEnrollment.student_id).where(
                SysUser.status == "normal", SysUser.user_type == "student")
    if members is not None:
        query = query.where(ProjectClass.teacher_id.in_(members))
    return db.execute(query).all()


def project_issues(db, students, now):
    from app.modules.student.models import ApplicationProgress, AcademicDeadline
    ticket = student_feedback_ticket.c
    complaints = set(db.scalars(select(ticket.student_id).where(
        ticket.student_id.in_(students), ticket.ticket_type == "complaint",
        ticket.status.in_(("pending", "processing")))))
    applications = set(db.scalars(select(ApplicationProgress.student_id).where(
        ApplicationProgress.student_id.in_(students), ApplicationProgress.stage != "enrolled",
        ApplicationProgress.deadline < now.date())))
    deadlines = set(db.scalars(select(AcademicDeadline.student_id).where(
        or_(AcademicDeadline.student_id.in_(students), AcademicDeadline.student_id.is_(None)),
        AcademicDeadline.status.in_(("pending", "reminded", "missed")),
        AcademicDeadline.deadline < now)))
    if None in deadlines:
        deadlines = set(students)
    return complaints, applications, deadlines


def project_names(db, ids):
    from app.modules.visitor.catalog import _courses
    return dict(db.execute(select(_courses.c.id, _courses.c.project_name).where(_courses.c.id.in_(ids))).all())
