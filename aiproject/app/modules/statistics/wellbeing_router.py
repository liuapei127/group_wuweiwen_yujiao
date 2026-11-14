from datetime import date
from typing import Annotated

from fastapi import APIRouter, Path

from app.core.responses import success
from app.core.security.authorization import require_permission, require_student_scope
from app.modules.student.router import Database, Principal, _student_id

from . import wellbeing as service
from .board_router import DB, Staff, Offset, Limit
from .periods import beijing_now

student_router = APIRouter(prefix="/api/v1/student/wellbeing", tags=["学生自评"])
staff_router = APIRouter(prefix="/api/v1/reporting/wellbeing", tags=["心理周报与关怀"])
RecordId = Annotated[int, Path(ge=1, le=2**63 - 1)]


@student_router.get("")
def panel(db: Database, principal: Principal):
    return success(service.student_panel(db, _student_id(db, principal)))


@student_router.put("/consent")
def consent(body: service.ConsentInput, db: Database, principal: Principal):
    return success(service.save_consent(db, _student_id(db, principal, lock=True), body))


@student_router.post("/check-ins", status_code=201)
def checkin(body: service.CheckinInput, db: Database, principal: Principal):
    return success(service.save_checkin(db, _student_id(db, principal, lock=True), body))


@student_router.post("/care", status_code=201)
def ask_care(body: service.CareInput, db: Database, principal: Principal):
    return success(service.open_case(db, _student_id(db, principal, lock=True), body.note))


@staff_router.get("/week")
def week(db: DB, staff: Staff, anchor: date | None = None):
    return success(service.desk_week(db, staff, anchor or beijing_now().date()))


@staff_router.post("/reports", status_code=201)
def generate(body: service.ReportInput, db: DB, staff: Staff):
    return success(service.generate(db, staff, body))


@staff_router.post("/reports/{archive_id}/review")
def review(archive_id: RecordId, body: service.ReviewInput, db: DB, staff: Staff):
    return success(service.review(db, staff, archive_id, body))


@staff_router.get("/cases")
def cases(db: DB, staff: Staff, offset: Offset = 0, limit: Limit = 30):
    return success(service.staff_cases(db, staff, offset, limit))


@staff_router.post("/cases", status_code=201)
def new_case(body: service.StaffCareInput, db: DB, staff: Staff):
    require_student_scope(staff, body.student_id, "student-alerts:write")
    return success(service.open_case(db, body.student_id, body.note, staff.employee_id))


@staff_router.get("/cases/{case_id}")
def case(case_id: RecordId, db: DB, staff: Staff):
    return success(service.case_detail(db, staff, case_id))


@staff_router.post("/cases/{case_id}/follow-ups", status_code=201)
def follow(case_id: RecordId, body: service.FollowupInput, db: DB, staff: Staff):
    return success(service.followup(db, staff, case_id, body))


@staff_router.get("/calendar")
def calendar(db: DB, staff: Staff):
    require_permission(staff, "student-alerts:read")
    return success(service.events(db, staff))


@staff_router.post("/calendar", status_code=201)
def new_event(body: service.EventInput, db: DB, staff: Staff):
    require_permission(staff, "student-alerts:write")
    return success(service.make_event(db, staff, body))
