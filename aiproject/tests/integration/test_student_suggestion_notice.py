"""Suggestions and complaints both close the student feedback loop."""
import pytest
from sqlalchemy import select, func
from tests.integration.test_student_complaint_flow import db
from app.core.security import EmployeePrincipal
from app.core.exceptions import BusinessError
from app.modules.feedback import service
from app.modules.feedback.schemas import StudentComplaintCreate, TicketUpdate
from app.modules.todo.models import notification_log, todo_item


@pytest.mark.parametrize("kind,title", [("complaint", "投诉处理结果"), ("suggestion", "建议处理结果")])
def test_each_feedback_type_notifies_once_after_resolution(db, kind, title):
    actor = EmployeePrincipal(3, frozenset({"tickets:read", "tickets:write"}), role_code="team_leader")
    row = service.submit_student_complaint(db, 1, StudentComplaintCreate(
        ticket_type=kind, category="learning", content="希望改善答疑安排"))
    service.process_ticket(row.id, TicketUpdate(expected_status="pending", status="processing"), db, actor)
    done = TicketUpdate(expected_status="processing", status="resolved", solution="已安排答疑")
    service.process_ticket(row.id, done, db, actor)
    notices = list(db.execute(select(notification_log).where(notification_log.c.related_id == row.id)).mappings())
    assert len(notices) == 1 and notices[0]["title"] == title
    assert db.scalar(select(todo_item.c.status).where(todo_item.c.related_id == row.id)) == "done"
    with pytest.raises(BusinessError):
        service.process_ticket(row.id, done, db, actor)
    assert db.scalar(select(func.count()).select_from(notification_log)) == 1
