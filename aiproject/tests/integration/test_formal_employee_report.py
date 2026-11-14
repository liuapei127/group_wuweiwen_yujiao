import json
from datetime import date, datetime

import httpx
from sqlalchemy import text, update
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import EmployeePrincipal
from app.modules.auth import service as auth_service
from app.modules.employee_report.models import EmployeeDailyReport
from app.modules.statistics import formal_dify, scheduled, service as statistics_service
from app.modules.student_admin.models import SysUser
from tests.integration.test_ent_portal_routes import isolated_portal


def test_formal_report_sends_only_latest_submitted_rows_in_authorized_department(isolated_portal, monkeypatch):
    app, engine = isolated_portal("trusted_jwt")
    monkeypatch.setattr(statistics_service, "get_settings", lambda: Settings(
        _env_file=None, employee_identity_mode="trusted_jwt", auth_jwt_secret="s" * 48
    ))
    read = "reports:summary:read"
    generate = "reports:formal:generate"
    actors = {
        "manager": EmployeePrincipal(10, frozenset({read, generate}), role_code="manager"),
        "reader": EmployeePrincipal(10, frozenset({read}), role_code="manager"),
        "writer": EmployeePrincipal(10, frozenset({generate}), role_code="manager"),
        "admin": EmployeePrincipal(12, frozenset({read, generate}), role_code="admin"),
    }
    monkeypatch.setattr(auth_service.AuthService, "authenticate", lambda self, token: actors[token])
    monkeypatch.setattr(formal_dify, "get_settings", lambda: Settings(
        _env_file=None, dify_employee_formal_api_key="rpt-test-key", dify_workflow_api_key="ent-test-key"
    ))
    sections = {
        "work_summary": "工作总结",
        "key_progress_summary": "关键进展",
        "risk_summary": "风险事项",
        "next_work_suggestions": "后续建议",
    }
    upstream_status = "ok"
    calls = []

    def upstream(request):
        calls.append(request)
        return httpx.Response(200, json={
            "data": {"status": "succeeded", "outputs": {
                **sections, "status": upstream_status, "error": "private upstream detail",
            }},
        })

    client_class = httpx.Client
    monkeypatch.setattr(formal_dify.httpx, "Client", lambda **options: client_class(
        transport=httpx.MockTransport(upstream), **options
    ))
    try:
        with Session(engine) as db:
            db.execute(text("""CREATE TABLE report_generation(
                id INTEGER PRIMARY KEY, report_type TEXT, report_title TEXT, report_content JSON,
                period_start DATE, period_end DATE, generated_by INTEGER, status TEXT, create_time DATETIME
            )"""))
            db.execute(text("""CREATE TABLE report_schedule(
                id INTEGER PRIMARY KEY, report_type TEXT, schedule_cron TEXT, recipients JSON, enabled INTEGER,
                last_run_time DATETIME, create_time DATETIME, update_time DATETIME
            )"""))
            db.add_all([
                SysUser(id=10, real_name="主管", user_type="employee", department="A"),
                SysUser(id=13, real_name="员工甲", user_type="employee", department="A"),
                SysUser(id=20, real_name="员工乙", user_type="employee", department="B"),
            ])
            db.add_all([
                EmployeeDailyReport(
                    id=idx, employee_id=employee, report_date=date(2026, 11, day),
                    content=content, status=status, create_time=datetime(2026, 11, day),
                    raw_content="private raw dictation",
                )
                for idx, (employee, day, content, status) in enumerate([
                    (13, 9, "old version", "submitted"), (13, 9, "latest version", "submitted"),
                    (13, 10, "next日", "submitted"), (10, 10, "draft content", "draft"),
                    (20, 9, "other department", "submitted"), (13, 16, "outside week", "submitted"),
                ], start=1)
            ])
            db.commit()

        def headers(actor):
            return {"Authorization": "Bearer " + actor}

        url = "/api/v1/reporting/employee-reports/formal-summary"
        weekly = {"anchor": "2026-11-11", "report_kind": "weekly"}
        with TestClient(app) as client:
            assert client.post(url, json=weekly).status_code == 401
            for actor in ("reader", "writer"):
                assert client.post(url, json=weekly, headers=headers(actor)).status_code == 403
            assert client.post(url, json={**weekly, "department": "B"}, headers=headers("manager")).status_code == 422
            assert not calls

            result = client.post(url, json=weekly, headers=headers("manager"))
            assert result.status_code == 200
            assert result.json()["data"]["sections"] == sections
            assert result.json()["data"]["statistics"]["submitted_employee_days"] == 2
            archive_url = "/api/v1/reporting/archive"
            archive_id = result.json()["data"]["archive_id"]
            pdf_url = f"{archive_url}/{archive_id}/pdf"
            archived = client.get(archive_url, headers=headers("manager")).json()["data"]
            assert [(r["id"], r["format"]) for r in archived] == [(archive_id, "formal")]
            assert archived[0]["report_content"]["sections"] == sections
            pdf = client.get(pdf_url, headers=headers("manager"))
            assert pdf.headers["content-type"] == "application/pdf"
            assert pdf.headers["cache-control"] == "no-store"
            assert pdf.content.startswith(b"%PDF-")
            assert client.get(pdf_url).status_code == 401
            assert client.get(pdf_url, headers=headers("admin")).status_code == 404
            assert client.get(pdf_url, headers=headers("reader")).status_code == 403
            sent = calls[-1]
            assert sent.headers["Authorization"] == "Bearer rpt-test-key"
            assert sent.url.path.endswith("/workflows/run")
            inputs = json.loads(sent.content)["inputs"]
            assert inputs["report_kind"] == "weekly"
            payload = json.loads(inputs["report_payload"])
            assert payload["period"] == {"start": "2026-11-09", "end": "2026-11-15"}
            assert [row["content"] for row in payload["employees"]] == ["latest version", "next日"]
            assert "private raw dictation" not in inputs["report_payload"]
            assert all("raw_content" not in row for row in payload["employees"])

            daily = {"anchor": "2026-11-09", "report_kind": "daily"}
            assert client.post(url, json=daily, headers=headers("admin")).status_code == 200
            inputs = json.loads(calls[-1].content)["inputs"]
            assert {row["department"] for row in json.loads(inputs["report_payload"])["employees"]} == {"A", "B"}

            upstream_status = "invalid"
            failed = client.post(url, json=daily, headers=headers("manager"))
            assert failed.status_code == 502 and "private upstream detail" not in failed.text

            previous_calls = len(calls)
            empty = client.post(url, json={**daily, "anchor": "2026-11-01"}, headers=headers("manager"))
            assert empty.json()["data"]["sections"]["work_summary"] == "本期无相关记录"
            assert len(calls) == previous_calls
            assert empty.json()["data"]["archive_id"] != archive_id
            with Session(engine) as db:
                db.execute(update(SysUser).where(SysUser.id == 13).values(department="B"))
                db.commit()
            assert client.get(pdf_url, headers=headers("manager")).status_code == 403
        with Session(engine) as db:
            assert db.query(EmployeeDailyReport).count() == 6
            assert db.scalar(text("SELECT COUNT(*) FROM report_generation")) == 3
            db.execute(text("""INSERT INTO report_schedule
                (report_type, schedule_cron, recipients, enabled, create_time)
                VALUES ('weekly_summary', '0 9 * * 1', '[12]', 1, '2026-11-15 10:00:00')
            """))
            db.commit()
            monkeypatch.setattr(scheduled, "_now", lambda: datetime(2026, 11, 16, 10))
            monkeypatch.setattr(scheduled.AuthRepository, "account", lambda self, **kwargs: {
                "status": "normal", "user_type": "admin", "role_status": 1, "role_id": 1, "role_code": "admin",
            })
            monkeypatch.setattr(scheduled.AuthRepository, "permissions", lambda self, role_id: {read})
            monkeypatch.setattr(scheduled.AuthRepository, "scope", lambda self, user_id: set())
            assert scheduled.scan_reports(db) == 1
            assert scheduled.scan_reports(db) == 0
            snapshot = scheduled.archive(db, actors["admin"], None)[0]
            assert snapshot["report_content"]["days"][0] == {
                "report_date": "2026-11-09", "submitted_employees": 2,
            }
    finally:
        engine.dispose()
