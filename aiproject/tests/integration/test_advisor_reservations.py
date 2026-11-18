from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.security import EmployeePrincipal
from app.core.security.credentials import utc_now
from app.modules.auth import service as auth_service
from app.modules.consultant.models import VisitorIntake
from app.modules.events import service as events
from app.modules.events.models import EventLecture, EventRegistration
from app.modules.events.schemas import EventCreate
from tests.integration.test_ent_portal_routes import isolated_portal
from tests.integration.test_event_booking import EVENT, ORGANIZER, seed_visitors


def test_advisor_reads_only_current_claims_and_sees_booking_lifecycle(isolated_portal, monkeypatch):
    app, engine = isolated_portal('trusted_jwt')
    read = frozenset({'visitor-intake:read'})
    principals = {
        'owner': EmployeePrincipal(10, read), 'other': EmployeePrincipal(12, read),
        'no-read': EmployeePrincipal(10), 'organizer': ORGANIZER,
        'admin': EmployeePrincipal(13, read, role_code='admin'),
    }
    monkeypatch.setattr(auth_service.AuthService, 'authenticate', lambda self, token: principals[token])
    headers = lambda token: {'Authorization': 'Bearer ' + token}
    base = '/api/v1/consultant/visitor-intake'
    endpoint = base + '/101/reservations'
    try:
        with Session(engine) as db:
            seed_visitors(db, 101, 102, 103, 104)
            db.add_all(VisitorIntake(visitor_id=vid, advisor_id=advisor, claimed_at=utc_now())
                       for vid, advisor in [(101, 10), (102, 12), (104, 10)])
            db.commit()
            event = events.create_event(db, EventCreate.model_validate({**EVENT, 'max_participants': 3}), ORGANIZER)
            own = events.reserve(db, event.id, customer_id=101)
            events.reserve(db, event.id, customer_id=102)
            events.reserve(db, event.id, customer_id=103)
        with TestClient(app) as client:
            assert client.get(endpoint).status_code == 401
            assert client.get(endpoint, headers=headers('no-read')).status_code == 403
            for token, visitor_id in [('other', 101), ('owner', 102), ('owner', 103), ('owner', 999), ('admin', 101)]:
                assert client.get(f'{base}/{visitor_id}/reservations', headers=headers(token)).status_code == 404
            assert client.get(base + '/104/reservations', headers=headers('owner')).json()['data'] == []
            response = client.get(endpoint, headers=headers('owner'))
            assert response.status_code == 200, response.text
            [record] = response.json()['data']
            assert record['id'] == own.id and record['event_id'] == event.id
            assert record['event_name'] == EVENT['event_name'] and record['location'] == EVENT['location']
            assert record['status'] == 'registered' and record['attended_at'] is None
            assert record['start_time'] == EVENT['start_time']
            assert record['reserved_at']
            assert 'customer_id' not in record and 'checked_in_by' not in record

            checkin = f'/api/v1/enterprise/events/{event.id}/registrations/{own.id}/check-in'
            assert client.post(checkin, headers=headers('owner')).status_code == 403
            assert client.get(f'/api/v1/enterprise/events/{event.id}/registrations', headers=headers('owner')).status_code == 403
            assert client.post(checkin, headers=headers('organizer')).status_code == 200
            checked = client.get(endpoint, headers=headers('owner')).json()['data'][0]
            assert checked['status'] == 'attended' and checked['attended_at']

            with Session(engine) as db:
                second = events.create_event(db, EventCreate.model_validate({**EVENT, 'event_name': '第二场活动'}), ORGANIZER)
                cancelled = events.reserve(db, second.id, customer_id=101)
                events.cancel(db, second.id, customer_id=101)
                db.execute(update(EventLecture).where(EventLecture.id == second.id).values(is_published=False))
                db.commit()
            first_page = client.get(endpoint, headers=headers('owner'), params={'limit': 1}).json()['data']
            assert first_page[0]['id'] == cancelled.id and first_page[0]['cancelled_at']
            assert first_page[0]['status'] == 'cancelled'
            next_page = client.get(endpoint, headers=headers('owner'), params={'limit': 1, 'before_id': cancelled.id}).json()['data']
            assert [row['id'] for row in next_page] == [own.id]
            assert client.get(endpoint, headers=headers('owner'), params={'before_id': own.id}).json()['data'] == []
            for invalid in [{'limit': 0}, {'limit': 101}, {'before_id': 0}]:
                assert client.get(endpoint, headers=headers('owner'), params=invalid).status_code == 422

            with Session(engine) as db:
                # Existing no-show states remain explicit; elapsed time alone does not invent one.
                db.execute(update(EventRegistration).where(EventRegistration.id == cancelled.id).values(
                    status='no_show', cancelled_at=None))
                db.execute(update(EventLecture).where(EventLecture.id == second.id).values(
                    status='ended', start_time=datetime(2020, 1, 1, 9), end_time=datetime(2020, 1, 1, 10)))
                db.commit()
            historical = client.get(endpoint, headers=headers('owner')).json()['data'][0]
            assert historical['event_status'] == 'ended' and historical['status'] == 'no_show'
            with Session(engine) as db:
                db.execute(update(VisitorIntake).where(VisitorIntake.visitor_id == 101).values(advisor_id=12))
                db.commit()
            assert client.get(endpoint, headers=headers('owner')).status_code == 404
            assert len(client.get(endpoint, headers=headers('other')).json()['data']) == 2
    finally:
        engine.dispose()
