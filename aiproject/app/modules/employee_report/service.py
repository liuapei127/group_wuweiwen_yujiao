from datetime import date

from sqlalchemy.orm import Session

from app.modules.employee_report.repository import EmployeeReportRepository
from app.modules.employee_report.schemas import DailyReportCreate


class EmployeeReportService:
    def __init__(self, db: Session):
        self.repo = EmployeeReportRepository(db)

    def submit(self, payload: DailyReportCreate):
        return self.repo.upsert(payload)

    def list_reports(self, employee_id: int | None, date_from: date | None, date_to: date | None):
        return self.repo.list_reports(employee_id, date_from, date_to)
