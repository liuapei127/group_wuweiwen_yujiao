"""Shared feedback visibility; personnel/company cases never enter a teacher inbox."""
import re

from sqlalchemy import and_, or_, not_


def manager_review(principal):
    return principal.role_code in ("admin", "manager")


def visible_tickets(columns, principal, *, assigned_only=False):
    owned = columns.assignee_id == principal.employee_id
    if manager_review(principal):
        return owned if assigned_only else or_(owned, columns.ticket_type.in_(("complaint", "suggestion")))
    return and_(owned, teacher_channel_filter(columns))


def teacher_channel_filter(columns):
    personnel = or_(*(field.like(pattern) for field in (columns.content, columns.title)
                     for pattern in ("%投诉%班主任%", "%举报%班主任%", "%反馈%班主任%", "%反映%班主任%", "%班主任%投诉%", "%班主任%举报%")))
    # coalesce prevents a missing title from turning the exclusion into SQL NULL.
    from sqlalchemy import func
    return and_(or_(columns.category == "learning", and_(columns.category.is_(None), columns.ticket_type == "consult")),
                not_(func.coalesce(personnel, False)))


def teacher_channel(ticket):
    return (ticket["category"] == "learning" or ticket["category"] is None and ticket["ticket_type"] == "consult") and not personnel_complaint((ticket.get("title") or "") + " " + ticket["content"])


def can_process(ticket, principal):
    return ("tickets:write" in principal.permissions
            and ticket["assignee_id"] == principal.employee_id
            and (teacher_channel(ticket) or manager_review(principal)))


def personnel_complaint(text):
    """Only explicit complaints about the class teacher require the manager route."""
    return bool(re.search(r"(?:投诉|举报|反映|反馈).{0,12}班主任|班主任.{0,12}(?:投诉|举报)", text))
