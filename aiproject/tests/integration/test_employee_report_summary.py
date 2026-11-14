from datetime import date, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import EmployeePrincipal
from app.modules.auth import service as auth_service
from app.modules.employee_report.models import EmployeeDailyReport
from app.modules.student_admin.models import SysUser
from tests.integration.test_ent_portal_routes import isolated_portal


def test_summary_uses_portal_permission_and_server_owned_department(isolated_portal, monkeypatch):
    app, engine = isolated_portal("trusted_jwt")
    summary_permission = frozenset({"reports:summary:read"})
    principals = {
        "manager": EmployeePrincipal(10, summary_permission, role_code="manager"),
        "no-department": EmployeePrincipal(11, summary_permission, role_code="manager"),
        "admin": EmployeePrincipal(12, summary_permission, role_code="admin"),
        "ordinary": EmployeePrincipal(13, frozenset({"reports:read"}), role_code="employee"),
        "wrong-role": EmployeePrincipal(13, summary_permission, role_code="employee"),
    }
    monkeypatch.setattr(auth_service.AuthService, "authenticate", lambda self, token: principals[token])
    try:
        with Session(engine) as db:
            db.add_all([
                SysUser(id=10, real_name="主管", user_type="employee", department="A"),
                SysUser(id=11, real_name="主管", user_type="employee"),
                SysUser(id=13, real_name="同事", user_type="employee", department="A"),
                SysUser(id=20, real_name="同事", user_type="employee", department="B"),
                SysUser(id=21, real_name="停用账号", user_type="employee", department="A", status="disabled"),
            ])
            db.add_all([
                EmployeeDailyReport(
                    id=idx, employee_id=employee, report_date=date(2026, 11, day),
                    content="内部日报正文", status=status, create_time=datetime(2026, 11, day),
                )
                for idx, (employee, day, status) in enumerate([
                    (13, 9, "submitted"), (13, 9, "submitted"), (10, 10, "submitted"),
                    (13, 10, "draft"), (20, 9, "submitted"), (21, 9, "submitted"),
                    (13, 16, "submitted"),
                ], start=1)
            ])
            db.commit()

        def headers(token):
            return {"Authorization": "Bearer " + token}

        url = "/api/v1/reporting/employee-reports/summary"
        with TestClient(app) as client:
            query = {"anchor": "2026-11-11", "period": "week", "department": "B"}
            assert client.get(url, params=query).status_code == 401
            for actor in ("ordinary", "wrong-role", "no-department"):
                assert client.get(url, params=query, headers=headers(actor)).status_code == 403
            response = client.get(url, params=query, headers=headers("manager"))
            assert response.status_code == 200
            summary = response.json()["data"]
            assert summary["department"] == "A"
            assert (summary["period_start"], summary["period_end"]) == ("2026-11-09", "2026-11-15")
            assert summary["submitted_employee_days"] == 2
            assert [day["submitted_employees"] for day in summary["days"]] == [1, 1, 0, 0, 0, 0, 0]
            assert "内部日报正文" not in response.text

            daily = client.get(url, params={"anchor": "2026-11-09"}, headers=headers("admin"))
            assert daily.json()["data"]["days"] == [{"report_date": "2026-11-09", "submitted_employees": 2}]
            overflow = client.get(url, params={"anchor": "9999-12-31", "period": "week"}, headers=headers("admin"))
            assert overflow.status_code == 422
    finally:
        engine.dispose()
