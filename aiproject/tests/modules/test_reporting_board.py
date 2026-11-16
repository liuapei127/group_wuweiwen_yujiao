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

def test_customer_breakdowns_match_scoped_detail_and_include_existing_customers():
    from datetime import datetime

    from app.modules.consultant.models import CrmFollowUp, CrmLead
    from app.modules.consultant.status_events import LeadStatusEvent
    from app.modules.statistics.board_repository import lead_dashboard
    from app.modules.student_admin.models import SysUser

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[SysUser.__table__, CrmLead.__table__,
                                             CrmFollowUp.__table__, LeadStatusEvent.__table__])
    start, end = date(2026, 11, 9), date(2026, 11, 15)
    prior, now = datetime(2026, 10, 12), datetime(2026, 11, 12)
    with Session(engine) as db:
        db.add_all([
            SysUser(id=1, real_name="员工一", department="咨询部", user_type="employee"),
            SysUser(id=2, real_name="员工二", department="其他部门", user_type="employee"),
            CrmLead(id=1, customer_name="新客户", status="contacting", owner_employee_id=1,
                    source_channel="官网线索", create_time=now, update_time=now),
            CrmLead(id=2, customer_name="原有客户", status="signed", owner_employee_id=1,
                    create_time=prior, update_time=now),
            CrmLead(id=3, customer_name="其他部门客户", status="signed", owner_employee_id=2,
                    source_channel="官网线索", create_time=now, update_time=now),
            CrmLead(id=4, customer_name="未填部门客户", status="new", owner_employee_id=4,
                    source_channel=" ", create_time=now, update_time=now),
            LeadStatusEvent(id=1, lead_id=2, status="signed", occurred_at=now),
            LeadStatusEvent(id=2, lead_id=3, status="signed", occurred_at=now),
            CrmFollowUp(id=1, lead_id=2, employee_id=1, follow_type="phone", content="约定回访", create_time=now),
            CrmFollowUp(id=2, lead_id=3, employee_id=2, follow_type="phone", content="跟进", create_time=now),
            CrmFollowUp(id=3, lead_id=2, employee_id=1, content="补充联系记录", create_time=now),
        ])
        db.commit()
        args = (db, "咨询部", start, end)
        summary = lead_dashboard(*args, None, 0, 30)
        assert summary["leads_by_status"] == {"contacting": 1}
        assert summary["departments"] == [{"department": "咨询部", "new": 1, "signed": 1, "lost": 0}]
        assert summary["source_channels"] == {"官网线索": 1}
        assert summary["follow_ups"] == {"phone": 1, "未填写": 1}
        for metric, bucket, expected in (("status", "contacting", 1), ("channel", "官网线索", 1),
                                         ("follow_up", "phone", 2), ("signed", None, 2)):
            result = lead_dashboard(*args, metric, 0, 30, bucket=bucket, department="咨询部")
            assert [item["id"] for item in result["items"]] == [expected]
        assert not lead_dashboard(*args, "signed", 0, 30, department="其他部门")["items"]
        unassigned = lead_dashboard(db, None, start, end, "new", 0, 30, department_missing=True)
        assert [item["id"] for item in unassigned["items"]] == [4]
        assert unassigned["source_channels"]["未填写"] == 1
    engine.dispose()


def test_complaint_comparisons_and_backlog_bands_use_scoped_tickets():
    from datetime import datetime, timedelta

    from app.modules.feedback.models import student_feedback_ticket
    from app.modules.statistics.board_repository import complaint_dashboard
    from app.modules.statistics.board_service import _complaint_comparison_periods
    from app.modules.student_admin.models import SysUser

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[SysUser.__table__, student_feedback_ticket])
    start, end = date(2026, 11, 9), date(2026, 11, 15)
    now = datetime(2026, 11, 16, 12)
    periods = _complaint_comparison_periods(start, end)
    assert periods["previous"] == (date(2026, 11, 2), date(2026, 11, 8))
    assert _complaint_comparison_periods(date(2024, 2, 1), date(2024, 2, 29)) == {
        "previous": (date(2024, 1, 1), date(2024, 1, 31)),
        "year_ago": (date(2023, 2, 1), date(2023, 2, 28)),
    }
    with Session(engine) as db:
        db.add_all([SysUser(id=i, real_name=str(i), department=dept, user_type="employee")
                    for i, dept in enumerate(("咨询部", "其他部门"), 1)])
        db.execute(student_feedback_ticket.insert(), [
            {"id": i, "student_id": i, "assignee_id": owner, "ticket_type": kind, "category": "服务沟通",
             "content": "测试", "status": "pending", "priority": "low", "satisfaction": 4, "is_notified": 0,
             "create_time": created, "update_time": created}
            for i, (owner, kind, created) in enumerate([
                (1, "complaint", now - timedelta(days=3)), (1, "complaint", datetime(2026, 11, 6)),
                (2, "complaint", now - timedelta(days=3)), (1, "suggestion", now - timedelta(days=3)),
            ], 1)
        ])
        db.commit()
        args = (db, "咨询部", start, end, now)
        result = complaint_dashboard(*args, "backlog", 0, 30, bucket="3–6 天", comparison_periods=periods)
        assert result["comparisons"]["previous"] == {"start": date(2026, 11, 2), "end": date(2026, 11, 8),
                                                        "count": 1, "change": 0, "percent": 0.0}
        assert result["comparisons"]["year_ago"]["percent"] is None
        assert result["backlog"]["0–2 天"] == 0
        assert result["backlog"]["3–6 天"] == 1
        assert [item["id"] for item in result["items"]] == [1]
        for metric, bucket in (("status", "pending"), ("category", "服务沟通"), ("satisfaction", "4")):
            assert [item["id"] for item in complaint_dashboard(*args, metric, 0, 30, bucket=bucket)["items"]] == [1]
    engine.dispose()


def test_wellbeing_reuses_draft_and_rejects_empty_archive(monkeypatch):
    from sqlalchemy import Column, Integer, MetaData, Table, func, select

    from app.core.security import EmployeePrincipal
    from app.modules.statistics import scheduled_repository, wellbeing
    from app.modules.student_admin.models import SysUser

    engine = create_engine("sqlite://")
    SysUser.__table__.create(engine)
    generated = scheduled_repository.generated
    Table("report_generation", MetaData(), Column("id", Integer, primary_key=True),
          *(Column(col.name, col.type) for col in generated.c if col.name != "id")).create(engine)
    principal = EmployeePrincipal(1, frozenset({"student-alerts:read", "student-alerts:write"}),
                                  student_ids=frozenset({1, 2, 3, 4, 5}))
    stats = {"period_start": date(2026, 11, 9), "period_end": date(2026, 11, 15), "eligible": 5,
             "participants": None, "suppressed": True, "items": [], "emotion": [], "stress": []}
    monkeypatch.setattr(wellbeing, "desk_week", lambda *_: stats)
    monkeypatch.setattr(wellbeing.report_ai, "suggest", lambda *_: "建议安排回访")
    with Session(engine) as db:
        db.add(SysUser(id=1, real_name="测试教师", user_type="employee"))
        db.commit()
        body = wellbeing.ReportInput(anchor=date(2026, 11, 9))
        with pytest.raises(BusinessError, match="暂无可归档"):
            wellbeing.generate(db, principal, body)
        assert db.scalar(select(func.count()).select_from(generated)) == 0
        stats.update(participants=5, suppressed=False)
        draft = wellbeing.generate(db, principal, body)
        result = wellbeing.generate(db, principal, wellbeing.ReportInput(anchor=date(2026, 11, 12), include_ai=True))
        assert result["archive_id"] == draft["archive_id"]
        assert result["ai_summary"] == "建议安排回访"
        assert wellbeing.generate(db, principal, body)["ai_summary"] == result["ai_summary"]
        assert db.scalar(select(func.count()).select_from(generated)) == 1
        wellbeing.review(db, principal, draft["archive_id"], wellbeing.ReviewInput(suggestion="安排回访"))
        revision = wellbeing.generate(db, principal, body)
        assert revision["archive_id"] != draft["archive_id"]
        assert db.scalar(select(func.count()).select_from(generated)) == 2
    engine.dispose()

def test_manager_daily_board_scopes_roster_and_submission_counts():
    from datetime import datetime

    from sqlalchemy import Column, MetaData, Table

    from app.modules.employee_report.models import EmployeeDailyReport
    from app.modules.organization.membership import members
    from app.modules.organization.models import sys_organization
    from app.modules.statistics.board_repository import employee_board
    from app.modules.student_admin.models import SysUser

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[SysUser.__table__, EmployeeDailyReport.__table__, sys_organization])
    membership = Table("sys_org_member", MetaData(), *(Column(col.name, col.type) for col in members.c))
    membership.create(engine)
    timestamp = datetime(2025, 12, 1)
    with Session(engine) as db:
        db.add_all([SysUser(id=i, real_name=str(i), department="咨询部", user_type="employee") for i in (1, 2, 3)])
        db.execute(sys_organization.insert(), {"id": 1, "org_name": "咨询部", "manager_id": 1, "org_level": 1,
                                               "sort_order": 0, "status": 1, "create_time": timestamp,
                                               "update_time": timestamp})
        db.execute(membership.insert(), {"id": 1, "user_id": 2, "org_id": 1, "status": "active",
                                         "effective_from": timestamp})
        db.add_all([EmployeeDailyReport(id=i, employee_id=i, report_date=timestamp.date(), content="日报",
                                        create_time=timestamp) for i in (2, 3)])
        db.commit()
        depts, rows = employee_board(db, 1, timestamp.date(), timestamp.date(), None, None, 0, 30)
        assert depts == [{"department": "咨询部", "expected": 1, "submitted": 1}]
        assert [row["employee_id"] for row in rows] == [2]
    engine.dispose()
