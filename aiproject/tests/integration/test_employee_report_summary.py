import json
from datetime import date, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import EmployeePrincipal
from app.modules.auth import service as auth_service
from app.modules.employee_report.models import EmployeeDailyReport, WeeklySubmission
from app.modules.statistics import formal_dify, service as statistics_service
from app.modules.statistics.schemas import FormalReportSections
from app.modules.student_admin.models import SysUser
from tests.integration.test_ent_portal_routes import isolated_portal


def test_individual_summary_scopes_sources_and_checks_changes(isolated_portal, monkeypatch):
    app, engine = isolated_portal("trusted_jwt")
    monkeypatch.setattr(statistics_service, "get_settings", lambda: Settings(
        _env_file=None, employee_identity_mode="trusted_jwt",
    ))
    read, generate = "reports:summary:read", "reports:formal:generate"
    actors = {
        "manager": EmployeePrincipal(10, frozenset({read, generate}), role_code="manager"),
        "reader": EmployeePrincipal(10, frozenset({read}), role_code="manager"),
        "writer": EmployeePrincipal(10, frozenset({generate}), role_code="manager"),
    }
    monkeypatch.setattr(auth_service.AuthService, "authenticate", lambda self, token: actors[token])
    sections = FormalReportSections(
        work_summary="完成咨询回访", key_progress_summary="跟进八位客户",
        risk_summary="尚待补交材料", next_work_suggestions="明日继续核对材料",
    )
    calls = []
    change = None

    def summarize(kind, payload):
        calls.append((kind, json.loads(payload)))
        if change:
            with Session(engine) as db:
                if change == "content":
                    db.execute(update(EmployeeDailyReport).where(EmployeeDailyReport.id == 2).values(content="更新后的原文"))
                else:
                    db.execute(update(SysUser).where(SysUser.id == 13).values(department="B"))
                db.commit()
        return sections

    monkeypatch.setattr(formal_dify, "generate_summary", summarize)
    day = date(2026, 11, 16)
    try:
        with Session(engine) as db:
            db.add_all([
                SysUser(id=i, real_name=name, user_type="employee", department=dept)
                for i, name, dept in [(10, "主管", "A"), (13, "员工甲", "A"), (14, "未提交员工", "A"), (20, "员工乙", "B")]
            ])
            for i, employee, content, status in [
                (1, 13, "原来版本", "submitted"), (2, 13, "今日原文", "submitted"),
                (3, 13, "未提交的草稿", "draft"), (4, 20, "另一部门", "submitted"),
            ]:
                db.add(EmployeeDailyReport(
                    id=i, employee_id=employee, report_date=day, content=content, raw_content="private dictation",
                    key_progress={"follow_ups": 8}, risks={"items": []}, status=status, create_time=datetime(2026, 11, 16),
                ))
            db.add(WeeklySubmission(
                employee_id=13, week_start=day, content="本周原文", submitted_at=datetime(2026, 11, 16),
            ))
            db.commit()
        url = "/api/v1/reporting/board/employees/13/summary?anchor=2026-11-16"
        headers = {"Authorization": "Bearer manager"}
        with TestClient(app) as client:
            assert client.post(url).status_code == 401
            for actor in ("reader", "writer"):
                assert client.post(url, headers={"Authorization": "Bearer " + actor}).status_code == 403
            assert client.post(url.replace("/13/", "/20/"), headers=headers).status_code == 404
            assert client.post(url.replace("/13/", "/14/"), headers=headers).status_code == 422
            assert not calls

            response = client.post(url, headers=headers)
            assert response.status_code == 200
            assert response.json()["data"]["sections"] == sections.model_dump()
            assert calls[-1][0] == "daily"
            assert [r["content"] for r in calls[-1][1]["employees"]] == ["今日原文"]
            assert "private dictation" not in json.dumps(calls[-1], ensure_ascii=False)

            assert client.post(url + "&period=week", headers=headers).status_code == 200
            assert calls[-1][0] == "weekly"
            assert [r["content"] for r in calls[-1][1]["employees"]] == ["本周原文"]

            change = "content"
            assert client.post(url, headers=headers).status_code == 409
            change = "scope"
            assert client.post(url, headers=headers).status_code == 404
    finally:
        engine.dispose()
