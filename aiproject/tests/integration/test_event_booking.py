from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.security import EmployeePrincipal
from app.modules.auth import service as auth_service
from app.modules.events import service
from app.modules.events.models import EventLecture, EventRegistration
from app.modules.events.schemas import EventCreate
from app.modules.visitor.router import require_visitor
from app.modules.visitor.service import VisitorPrincipal
from tests.integration.test_ent_portal_routes import isolated_portal


EVENT = {
    "event_name": "留学讲座",
    "location": "校区报告厅",
    "start_time": "2099-12-01T09:00:00",
    "end_time": "2099-12-01T11:00:00",
    "max_participants": 1,
}
PERMISSIONS = frozenset({"events:manage", "events:check_in"})
ORGANIZER = EmployeePrincipal(11, PERMISSIONS)


def test_reservation_cancel_and_staff_check_in(monkeypatch, isolated_portal):
    app, engine = isolated_portal("trusted_jwt")
    actors = {"organizer": ORGANIZER, "other": EmployeePrincipal(12, PERMISSIONS)}
    monkeypatch.setattr(auth_service.AuthService, "authenticate", lambda self, token: actors[token])
    base = "/api/v1/enterprise/events"
    organizer = {"Authorization": "Bearer organizer"}
    other = {"Authorization": "Bearer other"}
    try:
        with TestClient(app) as client, Session(engine) as db:
            assert client.post(base, json=EVENT).status_code == 401
            event_id = client.post(base, json=EVENT, headers=organizer).json()["data"]["id"]
            assert [row["id"] for row in client.get(base, headers=organizer).json()["data"]] == [event_id]
            assert client.get(base, headers=other).json()["data"] == []
            booked = service.reserve(db, event_id, customer_id=101)
            assert service.reserve(db, event_id, customer_id=101).id == booked.id
            with pytest.raises(BusinessError) as full:
                service.reserve(db, event_id, customer_id=102)
            assert full.value.status_code == 409
            with pytest.raises(BusinessError) as not_owned:
                service.cancel(db, event_id, customer_id=102)
            assert not_owned.value.status_code == 404
            assert service.cancel(db, event_id, customer_id=101).status == "cancelled"
            assert service.cancel(db, event_id, customer_id=101).status == "cancelled"

            registrations = f"{base}/{event_id}/registrations"
            assert client.post(f"{registrations}/{booked.id}/check-in", headers=organizer).status_code == 409
            replacement = service.reserve(db, event_id, customer_id=102)
            assert client.get(registrations, headers=other).status_code == 403
            rows = client.get(registrations, headers=organizer).json()["data"]
            assert [row["customer_id"] for row in rows] == [101, 102]
            check_in = f"{registrations}/{replacement.id}/check-in"
            assert client.post(check_in, headers=other).status_code == 403
            result = client.post(check_in, headers=organizer).json()["data"]
            assert result["status"] == "attended"
            assert result["attended_at"]
            assert result["checked_in_by"] == ORGANIZER.employee_id
            assert client.post(check_in, headers=organizer).status_code == 409
            with pytest.raises(BusinessError) as attended:
                service.cancel(db, event_id, customer_id=102)
            assert attended.value.status_code == 409
            assert db.get(EventLecture, event_id).current_participants == 1
    finally:
        engine.dispose()


def test_event_management_controls_booking_visibility(monkeypatch, isolated_portal):
    app, engine = isolated_portal("trusted_jwt")
    principals = {
        "organizer": ORGANIZER,
        "other": EmployeePrincipal(12, PERMISSIONS),
        "admin": EmployeePrincipal(13, PERMISSIONS, role_code="admin"),
        "check-in-only": EmployeePrincipal(11, frozenset({"events:check_in"})),
    }
    monkeypatch.setattr(auth_service.AuthService, "authenticate", lambda self, token: principals[token])
    app.dependency_overrides[require_visitor] = lambda: VisitorPrincipal(101, "test")
    events = "/api/v1/enterprise/events"
    visitor_events = "/api/v1/visitor/events"
    organizer = {"Authorization": "Bearer organizer"}
    admin = {"Authorization": "Bearer admin"}
    try:
        with TestClient(app) as client:
            draft = client.post(events, json={**EVENT, "is_published": False}, headers=organizer)
            assert draft.status_code == 200
            event = draft.json()["data"]
            assert event["is_published"] is False
            event_path = f"{events}/{event['id']}"
            publication = f"{event_path}/publication"
            reservation = f"{visitor_events}/{event['id']}/reservation"
            assert client.get(visitor_events).json()["data"] == []
            assert client.post(reservation).status_code == 409

            updated = {**EVENT, "event_name": "更新后的留学讲座", "location": "新报告厅"}
            for token in ("other", "check-in-only"):
                forbidden = {"Authorization": f"Bearer {token}"}
                assert client.put(event_path, json=updated, headers=forbidden).status_code == 403
                assert client.patch(publication, json={"is_published": True}, headers=forbidden).status_code == 403
                assert client.delete(event_path, headers=forbidden).status_code == 403
            assert client.put(event_path, json=updated, headers=admin).status_code == 200
            assert client.patch(publication, json={"is_published": True}, headers=admin).status_code == 200
            [visible] = client.get(visitor_events).json()["data"]
            assert visible["event_name"] == updated["event_name"]
            assert visible["location"] == updated["location"]
            assert client.patch(publication, json={"is_published": False}, headers=admin).status_code == 200
            assert client.get(visitor_events).json()["data"] == []
            assert client.post(reservation).status_code == 409
            assert client.delete(event_path, headers=admin).status_code == 200
            assert client.get(events, headers=admin).json()["data"] == []
    finally:
        engine.dispose()


def test_event_management_preserves_reservations_and_checks_start_time(monkeypatch, isolated_portal):
    app, engine = isolated_portal("trusted_jwt")
    monkeypatch.setattr(auth_service.AuthService, "authenticate", lambda self, token: ORGANIZER)
    app.dependency_overrides[require_visitor] = lambda: VisitorPrincipal(101, "test")
    events = "/api/v1/enterprise/events"
    visitor_events = "/api/v1/visitor/events"
    organizer = {"Authorization": "Bearer organizer"}
    past_event = {**EVENT, "start_time": "2000-01-01T09:00:00", "end_time": "2000-01-01T11:00:00"}
    try:
        with TestClient(app) as client:
            assert client.post(events, json=past_event, headers=organizer).status_code == 422
            draft_id = client.post(events, json={**past_event, "is_published": False},
                                   headers=organizer).json()["data"]["id"]
            assert client.patch(f"{events}/{draft_id}/publication", json={"is_published": True},
                                headers=organizer).status_code == 409

            event_id = client.post(events, json={**EVENT, "max_participants": 2},
                                   headers=organizer).json()["data"]["id"]
            event_path = f"{events}/{event_id}"
            reservation = f"{visitor_events}/{event_id}/reservation"
            assert client.post(reservation).status_code == 200
            app.dependency_overrides[require_visitor] = lambda: VisitorPrincipal(102, "test")
            assert client.post(reservation).status_code == 200
            assert client.put(event_path, json=EVENT, headers=organizer).status_code == 409
            assert client.patch(f"{event_path}/publication", json={"is_published": False},
                                headers=organizer).status_code == 200
            assert client.get(visitor_events).json()["data"] == []
            assert client.delete(reservation).status_code == 200
            app.dependency_overrides[require_visitor] = lambda: VisitorPrincipal(101, "test")
            assert client.delete(reservation).status_code == 200
            assert client.delete(event_path, headers=organizer).status_code == 409
            assert len(client.get(f"{event_path}/registrations", headers=organizer).json()["data"]) == 2
    finally:
        engine.dispose()


def test_concurrent_reservations_do_not_exceed_capacity(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'events.db'}")
    try:
        EventLecture.__table__.create(engine)
        EventRegistration.__table__.create(engine)
        with Session(engine) as db:
            event_id = service.create_event(db, EventCreate.model_validate(EVENT), ORGANIZER).id

        start = Barrier(4)

        def reserve(customer_id):
            with Session(engine) as db:
                start.wait(timeout=5)
                try:
                    return service.reserve(db, event_id, customer_id=customer_id).status
                except BusinessError as exc:
                    assert exc.status_code == 409
                    return "full"

        with ThreadPoolExecutor(max_workers=4) as pool:
            statuses = list(pool.map(reserve, range(101, 105)))
        assert statuses.count("registered") == 1
        assert statuses.count("full") == 3
    finally:
        engine.dispose()
