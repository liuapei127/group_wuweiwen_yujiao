from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import EmployeePrincipal
from app.modules.auth import service as auth_service
from app.modules.statistics import scheduled_repository, service as statistics_service
from tests.integration.test_ent_portal_routes import isolated_portal


def test_archive_filters_before_paging_and_preserves_access_scope(isolated_portal, monkeypatch):
    app, engine = isolated_portal("trusted_jwt")
    monkeypatch.setattr(statistics_service, "get_settings", lambda: Settings(
        _env_file=None, employee_identity_mode="trusted_jwt", auth_jwt_secret="s" * 48,
    ))
    read = "reports:summary:read"
    operate = "reports:operations:read"
    actors = {
        "owner": EmployeePrincipal(10, frozenset({read, operate}), role_code="admin"),
        "reader": EmployeePrincipal(10, frozenset({read}), role_code="admin"),
        "other": EmployeePrincipal(12, frozenset({read}), role_code="admin"),
    }
    monkeypatch.setattr(auth_service.AuthService, "authenticate", lambda self, token: actors[token])
    try:
        with Session(engine) as db:
            db.execute(text('''CREATE TABLE report_generation(
                id INTEGER PRIMARY KEY, report_type TEXT, report_title TEXT, report_content JSON,
                period_start DATE, period_end DATE, generated_by INTEGER, status TEXT, create_time DATETIME
            )'''))
            now = datetime(2026, 11, 16, 10)
            payload = {
                "period_start": "2026-11-09", "period_end": "2026-11-15",
                "scope_version": 1, "department": None, "statistics": {"days": []},
            }
            weekly_ids = [
                scheduled_repository.record_report(db, 10, "weekly_summary", f"周报{i}", payload, now)
                for i in range(7)
            ]
            complaint_id = scheduled_repository.record_report(db, 10, "complaint_weekly", "投诉周报", payload, now)
            daily_id = scheduled_repository.record_report(db, 10, "daily_summary", "日报", payload, now)
            other_id = scheduled_repository.record_report(db, 12, "weekly_summary", "他人周报", payload, now)
            scoped_id = scheduled_repository.record_report(
                db, 10, "weekly_summary", "范围已变化", {**payload, "department": "A"}, now,
            )
            db.commit()

        url = "/api/v1/reporting/archive"
        headers = {"Authorization": "Bearer owner"}
        query = {"kind": "weekly_summary", "limit": 6}
        with TestClient(app) as client:
            response = client.get(url, headers=headers, params=query)
            assert response.status_code == 200
            first = response.json()["data"]
            assert first[0] == {"id": scoped_id, "unavailable": True}
            assert [row["id"] for row in first[1:]] == weekly_ids[::-1][:5]

            # The sixth result is a lookahead. Paging starts after the fifth displayed row.
            response = client.get(url, headers=headers, params={**query, "before_id": first[4]["id"]})
            assert response.status_code == 200
            assert [row["id"] for row in response.json()["data"]] == weekly_ids[:3][::-1]

            all_rows = client.get(url, headers=headers).json()["data"]
            assert [row["id"] for row in all_rows] == [scoped_id, daily_id, complaint_id, *weekly_ids[::-1]]
            other_rows = client.get(url, headers={"Authorization": "Bearer other"}, params=query).json()["data"]
            assert [row["id"] for row in other_rows] == [other_id]
            assert client.get(url, headers={"Authorization": "Bearer reader"},
                              params={"kind": "complaint_weekly", "limit": 6}).status_code == 403
            assert client.get(url, headers=headers, params={"kind": "unknown"}).status_code == 422
            assert client.get(url, headers=headers, params={"limit": 21}).status_code == 422
    finally:
        engine.dispose()
