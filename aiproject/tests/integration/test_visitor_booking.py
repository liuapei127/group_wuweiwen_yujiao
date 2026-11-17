import hashlib
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.security import EmployeePrincipal
from app.core.security.credentials import utc_now
from app.modules.consultant.models import CrmLead
from app.modules.events import service as events
from app.modules.events.schemas import EventCreate
from app.modules.visitor.models import VisitorAccount, VisitorSession
from tests.integration.test_ent_portal_routes import isolated_portal


def test_registered_visitors_can_manage_only_own_booking(isolated_portal):
    app, engine = isolated_portal("trusted_jwt")
    identity = "/api/v1/visitors"
    listing = "/api/v1/visitor/events"
    password = "test-visitor-password"
    try:
        with Session(engine) as db:
            actor = EmployeePrincipal(1, frozenset({"events:manage"}))
            event_id = events.create_event(db, EventCreate.model_validate({
                "event_name": "讲座", "location": "报告厅", "max_participants": 1,
                "start_time": "2099-01-01T09:00:00", "end_time": "2099-01-01T10:00:00",
            }), actor).id
        reservation = f"{listing}/{event_id}/reservation"

        with TestClient(app) as client:
            assert client.post(reservation).status_code == 401
            registration = {"username": " 13900001001 ", "password": password, "name": "访客一", "contact": "contact"}
            one = client.post(identity + "/register", json=registration)
            assert one.status_code == 201
            token = one.json()["data"]["access_token"]
            assert client.post(identity + "/register", json=registration).status_code == 409
            assert client.post(identity + "/login", json={"username": "13900001001", "password": "wrong"}).status_code == 401
            login = client.post(identity + "/login", json={"username": "13900001001", "password": password})
            assert login.status_code == 200
            assert login.json()["data"]["access_token"] != token
            other_username = "13900001002"
            two = client.post(identity + "/register", json={
                "username": other_username, "password": password, "nickname": "游客昵称",
            })
            assert two.status_code == 201
            bearer = {"Authorization": "Bearer " + token}
            other = {"Authorization": "Bearer " + two.json()["data"]["access_token"]}
            profile = identity + "/profile"
            with Session(engine) as db:
                db.execute(update(VisitorAccount).where(VisitorAccount.username == other_username).values(contact=""))
                db.commit()
            other_profile = client.get(profile, headers=other).json()["data"]
            assert other_profile["name"] == "" and other_profile["contact"] == other_username

            assert client.get(listing, headers=bearer).json()["data"][0]["id"] == event_id
            assert client.get("/api/v1/auth/me", headers=bearer).status_code == 401
            assert client.post(reservation, headers=other).status_code == 422
            assert client.post(reservation, headers=other, json={"name": "   "}).status_code == 422
            assert client.post(reservation, headers=other, json={"name": "未填写姓名"}).status_code == 422
            assert client.get(listing, headers=other).json()["data"][0]["current_participants"] == 0
            assert client.post(reservation, headers=bearer).json()["data"]["status"] == "registered"
            assert client.get(listing, headers=bearer).json()["data"][0]["reservation_status"] == "registered"
            assert client.get(listing, headers=other).json()["data"][0]["reservation_status"] is None
            assert client.get(listing + "/reservations", headers=other).json()["data"] == []
            own_bookings = client.get(listing + "/reservations", headers=bearer).json()["data"]
            assert own_bookings[0]["reservation"]["status"] == "registered"
            assert client.delete(reservation, headers=other).status_code == 404
            details = {"name": "  访客二  "}
            assert client.post(reservation, headers=other, json=details).status_code == 409
            assert client.get(profile, headers=other).json()["data"]["name"] == ""
            assert client.delete(reservation, headers=bearer).json()["data"]["status"] == "cancelled"
            assert client.post(reservation, headers=other, json=details).status_code == 200
            assert client.post(reservation, headers=other, json={"name": "重复请求的姓名"}).status_code == 200
            completed = client.get(profile, headers=other).json()["data"]
            assert (completed["name"], completed["nickname"], completed["contact"]) == (
                "访客二", "游客昵称", other_username,
            )

            with Session(engine) as db:
                row = db.scalar(select(VisitorAccount).where(VisitorAccount.username == "13900001001"))
                assert (row.name, row.contact) == ("访客一", "contact")
                assert row.password_hash.startswith("$argon2")
                assert db.get(VisitorSession, hashlib.sha256(token.encode()).hexdigest())
                assert db.scalar(select(func.count()).select_from(CrmLead)) == 0
                digest = hashlib.sha256(two.json()["data"]["access_token"].encode()).hexdigest()
                db.execute(update(VisitorSession).where(VisitorSession.digest == digest).values(
                    expires_at=utc_now() - timedelta(seconds=1)
                ))
                db.commit()
            assert client.get(listing, headers=other).status_code == 401
            assert client.post(identity + "/logout", headers=bearer).status_code == 200
            assert client.get(listing, headers=bearer).status_code == 401
    finally:
        engine.dispose()
