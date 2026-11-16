from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.security import EmployeePrincipal
from app.core.security.authorization import require_permission

from . import repository
from .models import EventLecture, EventRegistration
from .schemas import (
    EventCreate, EventDetails, EventOut, RegistrationOut, StaffRegistrationOut, VisitorEventOut,
    VisitorReservationOut,
)


_BEIJING = timezone(timedelta(hours=8))


def _event_now() -> datetime:
    return datetime.now(_BEIJING).replace(tzinfo=None, microsecond=0)


def _require_event(db: Session, event_id: int, *, lock: bool = True) -> EventLecture:
    row = repository.event(db, event_id, lock=lock)
    if row is None:
        raise BusinessError(404, "活动不存在")
    return row


def _staff_event(db: Session, event_id: int, principal: EmployeePrincipal, *, lock: bool) -> EventLecture:
    row = _require_event(db, event_id, lock=lock)
    if row.organizer_id != principal.employee_id and principal.role_code != "admin":
        raise BusinessError(403, "当前员工无权管理该活动")
    return row


def create_event(db: Session, payload: EventCreate, principal: EmployeePrincipal) -> EventOut:
    require_permission(principal, "events:manage")
    now = _event_now()
    if payload.is_published and payload.start_time <= now:
        raise BusinessError(422, "发布活动时，开始时间必须晚于当前北京时间")
    try:
        row = EventLecture(**payload.model_dump(), organizer_id=principal.employee_id, create_time=now)
        db.add(row)
        db.flush()
        result = EventOut.model_validate(row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


def update_event(db: Session, event_id: int, payload: EventDetails, principal: EmployeePrincipal) -> EventOut:
    require_permission(principal, "events:manage")
    try:
        row = _staff_event(db, event_id, principal, lock=True)
        if payload.max_participants < row.current_participants:
            raise BusinessError(409, "名额上限不能低于已用名额")
        if row.is_published and payload.start_time != row.start_time and payload.start_time <= _event_now():
            raise BusinessError(422, "已发布活动的新开始时间必须晚于当前北京时间")
        for field, value in payload.model_dump().items():
            setattr(row, field, value)
        db.flush()
        result = EventOut.model_validate(row)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def set_publication(db: Session, event_id: int, is_published: bool, principal: EmployeePrincipal) -> EventOut:
    require_permission(principal, "events:manage")
    try:
        row = _staff_event(db, event_id, principal, lock=True)
        if is_published and not row.is_published:
            if row.status != "upcoming" or row.start_time <= _event_now():
                raise BusinessError(409, "只有尚未开始的活动可以发布")
            if row.max_participants is None:
                raise BusinessError(409, "请先设置预约名额")
        row.is_published = is_published
        db.flush()
        result = EventOut.model_validate(row)
        db.commit()
        return result
    except Exception:
        db.rollback()
        raise


def delete_event(db: Session, event_id: int, principal: EmployeePrincipal) -> None:
    require_permission(principal, "events:manage")
    try:
        row = _staff_event(db, event_id, principal, lock=True)
        if row.current_participants or repository.has_registrations(db, event_id):
            raise BusinessError(409, "该活动已有预约记录，请下架以保留预约历史")
        db.delete(row)
        db.commit()
    except Exception:
        db.rollback()
        raise


def upcoming_events(db: Session, customer_id: int, offset: int, limit: int) -> list[VisitorEventOut]:
    rows = repository.upcoming(db, _event_now(), offset, limit)
    bookings = repository.customer_bookings(db, customer_id, [row.id for row in rows])
    return [
        VisitorEventOut(**EventOut.model_validate(row).model_dump(), reservation_status=bookings.get(row.id))
        for row in rows
    ]


def public_schedule(
    db: Session, *, days: int, keyword: str = "", event_type: str | None = None,
) -> list[EventLecture]:
    now = _event_now()
    return repository.upcoming(
        db, now, 0, 10, before=now + timedelta(days=days), keyword=keyword,
        event_type=event_type, available_only=True,
    )


def visitor_reservations(
    db: Session, customer_id: int, before_id: int | None, limit: int,
) -> list[VisitorReservationOut]:
    return [
        VisitorReservationOut(event=EventOut.model_validate(event), reservation=RegistrationOut.model_validate(row))
        for event, row in repository.customer_reservations(db, customer_id, before_id, limit)
    ]


def list_staff_events(
    db: Session, principal: EmployeePrincipal, before_id: int | None, limit: int,
) -> list[EventOut]:
    if not {"events:manage", "events:check_in"} & principal.permissions:
        raise BusinessError(403, "缺少活动管理或签到权限")
    organizer_id = None if principal.role_code == "admin" else principal.employee_id
    return [EventOut.model_validate(row) for row in repository.staff_events(db, organizer_id, before_id, limit)]


def reserve(db: Session, event_id: int, *, customer_id: int) -> RegistrationOut:
    """customer_id 由可信游客身份提供。"""
    try:
        event = _require_event(db, event_id)
        row = repository.booking_for_customer(db, event_id, customer_id)
        if row is None or row.status == "cancelled":
            if not event.is_published:
                raise BusinessError(409, "活动未发布，无法预约")
            if event.status != "upcoming" or event.start_time <= _event_now():
                raise BusinessError(409, "活动已开始，无法预约")
            if event.max_participants is None:
                raise BusinessError(409, "该活动还未设置预约名额")
            if not repository.reserve_seat(db, event_id):
                raise BusinessError(409, "活动名额已满")
            if row is None:
                row = EventRegistration(event_id=event_id, customer_id=customer_id)
                db.add(row)
            row.status = "registered"
            row.cancelled_at = None
            row.create_time = _event_now()
            db.flush()
        result = RegistrationOut.model_validate(row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


def cancel(db: Session, event_id: int, *, customer_id: int) -> RegistrationOut:
    try:
        _require_event(db, event_id)
        row = repository.booking_for_customer(db, event_id, customer_id)
        if row is None:
            raise BusinessError(404, "预约不存在")
        if row.status == "attended":
            raise BusinessError(409, "已签到的预约无法取消")
        if row.status == "registered":
            if not repository.mark_cancelled(db, event_id, customer_id, _event_now()):
                raise BusinessError(409, "预约状态已变化")
            if not repository.release_seat(db, event_id):
                raise BusinessError(409, "活动名额记录不一致")
        result = RegistrationOut.model_validate(row)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result


def list_staff_registrations(
    db: Session, event_id: int, principal: EmployeePrincipal, after_id: int, limit: int
) -> list[StaffRegistrationOut]:
    require_permission(principal, "events:check_in")
    _staff_event(db, event_id, principal, lock=False)
    return [
        StaffRegistrationOut(**RegistrationOut.model_validate(row).model_dump(),
                             customer_id=row.customer_id, customer_name=name)
        for row, name in repository.registrations(db, event_id, after_id, limit)
    ]


def check_in(db: Session, event_id: int, registration_id: int, principal: EmployeePrincipal) -> RegistrationOut:
    require_permission(principal, "events:check_in")
    try:
        _staff_event(db, event_id, principal, lock=True)
        if not repository.mark_attended(db, event_id, registration_id, principal.employee_id, _event_now()):
            raise BusinessError(409, "预约不存在、已取消或已签到")
        result = RegistrationOut.model_validate(db.get(EventRegistration, registration_id))
        db.commit()
    except Exception:
        db.rollback()
        raise
    return result
