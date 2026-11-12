from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.modules.employee_report.models import EmployeeDailyReport
from app.modules.employee_report.schemas import DailyReportCreate
from app.shared.utils.time_util import now_naive


class EmployeeReportRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert(self, payload: DailyReportCreate) -> EmployeeDailyReport:
        report_date = payload.report_date or date.today()
        stmt = select(EmployeeDailyReport).where(
            EmployeeDailyReport.employee_id == payload.employee_id,
            EmployeeDailyReport.report_date == report_date,
        )
        existing = self.db.scalar(stmt)
        if existing:
            existing.raw_content = payload.raw_content or existing.raw_content
            existing.content = payload.content
            existing.key_progress = payload.key_progress
            existing.risks = payload.risks
            existing.next_plan = payload.next_plan
            existing.status = "submitted"
            self.db.commit()
            self.db.refresh(existing)
            return existing

        row = EmployeeDailyReport(
            employee_id=payload.employee_id,
            report_date=report_date,
            raw_content=payload.raw_content,
            content=payload.content,
            key_progress=payload.key_progress,
            risks=payload.risks,
            next_plan=payload.next_plan,
            status="submitted",
            create_time=now_naive(),
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row

    def list_reports(
        self,
        employee_id: int | None,
        date_from: date | None,
        date_to: date | None,
        limit: int = 100,
    ) -> list[EmployeeDailyReport]:
        stmt = select(EmployeeDailyReport)
        if employee_id:
            stmt = stmt.where(EmployeeDailyReport.employee_id == employee_id)
        if date_from:
            stmt = stmt.where(EmployeeDailyReport.report_date >= date_from)
        if date_to:
            stmt = stmt.where(EmployeeDailyReport.report_date <= date_to)
        stmt = stmt.order_by(EmployeeDailyReport.report_date.desc()).limit(limit)
        return list(self.db.scalars(stmt).all())
