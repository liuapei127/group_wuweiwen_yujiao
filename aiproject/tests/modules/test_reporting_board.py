from datetime import date

from app.modules.statistics import scheduled
from app.modules.statistics.wellbeing import ConsentInput, CheckinInput, save_checkin, save_consent, student_panel
from app.core.exceptions import BusinessError
from app.core.database import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

import pytest


def test_customer_schedule_keeps_daily_and_accepts_weekly():
    now = scheduled._now().replace(year=2026, month=11, day=18, hour=9, minute=0)
    assert scheduled._scheduled_time("30 8 * * *", "customer_ops", now).date() == date(2026, 11, 18)
    assert scheduled._scheduled_time("30 8 * * 1", "customer_ops", now).date() == date(2026, 11, 16)


def test_student_checkin_requires_consent_and_allows_one_editable_record():
    from app.modules.statistics.wellbeing_models import WellbeingConsent, WellbeingCheckin

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[WellbeingConsent.__table__, WellbeingCheckin.__table__])
    with Session(engine) as db:
        with pytest.raises(BusinessError) as blocked:
            save_checkin(db, 1, CheckinInput(emotion="poor", stress="moderate"))
        assert blocked.value.status_code == 403
        save_consent(db, 1, ConsentInput(granted=True, version="v1"))
        save_checkin(db, 1, CheckinInput(emotion="poor", stress="moderate"))
        save_checkin(db, 1, CheckinInput(emotion="good", stress="light"))
        reviewed = student_panel(db, 1)
        assert [item["emotion"] for item in reviewed["checkins"]] == ["good"]
        assert student_panel(db, 2)["checkins"] == []
        save_consent(db, 1, ConsentInput(granted=False, version="v1"))
        with pytest.raises(BusinessError):
            save_checkin(db, 1, CheckinInput(emotion="good", stress="none"))
    engine.dispose()

def test_conflict_scan_checks_source_excerpts_and_reuses_results(monkeypatch):
    from app.core.security import EmployeePrincipal
    from app.modules.statistics import employee_conflicts
    from app.modules.statistics.wellbeing_models import EmployeeReportConflict

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[EmployeeReportConflict.__table__])
    principal = EmployeePrincipal(1, frozenset({"reports:formal:generate"}))
    day = date(2026, 11, 14)
    monkeypatch.setattr(employee_conflicts, "employee_detail", lambda *args: {
        "reports": [{"report_date": day, "content": "签单 2 件", "key_progress": None}],
        "weekly_report": {"content": "签单 3 件", "key_progress": None},
    })
    monkeypatch.setattr(employee_conflicts.report_ai, "compare_reports", lambda *_: (
        '{"conflicts":[{"summary":"数量不同","daily_excerpt":"签单 2 件","weekly_excerpt":"签单 3 件"},'
        '{"summary":"编造","daily_excerpt":"不存在","weekly_excerpt":"签单 3 件"}]}'
    ))
    # This unit test isolates the persisted findings from the separate employee-account row lock.
    with Session(engine) as db:
        from app.modules.student_admin.models import SysUser

        SysUser.__table__.create(engine)
        db.add(SysUser(id=1, real_name="联调员工", user_type="employee", status="normal"))
        db.commit()
        assert len(employee_conflicts.scan(db, principal, 1, day)) == 1
        findings = employee_conflicts.scan(db, principal, 1, day)
        assert len(findings) == 1
        result = employee_conflicts.resolve(db, principal, findings[0]["id"],
                     employee_conflicts.Resolution(status="verified", verify_note="已核对"))
        assert result["status"] == "verified"
    engine.dispose()

def test_reporting_ai_uses_dify_when_direct_model_is_unconfigured(monkeypatch):
    import json
    from app.core.config import Settings
    from app.modules.statistics import report_ai
    from app.modules.statistics.schemas import FormalReportSections

    calls = []

    def run(kind, payload):
        calls.append((kind, json.loads(payload)))
        return FormalReportSections(
            work_summary='{"conflicts":[]}' if kind == "conflicts" else "群体报告示例",
            key_progress_summary="本期无相关记录", risk_summary="本期无相关记录", next_work_suggestions="本期无相关记录",
        )

    monkeypatch.setattr(report_ai, "get_settings", lambda: Settings(_env_file=None, dify_employee_formal_api_key="test"))
    monkeypatch.setattr(report_ai, "run_summary_workflow", run)
    assert report_ai.suggest("投诉", {"backlog": {"0–2 天": 2}}) == "群体报告示例"
    assert report_ai.suggest("心理周报", {"participants": 8}) == "群体报告示例"
    assert json.loads(report_ai.compare_reports(["日报"], "周报")) == {"conflicts": []}
    assert [kind for kind, _ in calls] == ["complaints", "wellbeing", "conflicts"]
    assert calls[0][1]["汇总"] == {"backlog": {"0–2 天": 2}}
