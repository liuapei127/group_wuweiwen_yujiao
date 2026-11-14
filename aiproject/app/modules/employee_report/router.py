from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from app.core.security import EmployeePrincipal, require_employee
from app.core.database import get_db
from app.core.responses import success
from app.modules.employee_report.schemas import DailyReportCreate, DailyReportOut
from app.modules.employee_report.service import EmployeeReportService
from .weekly import WeeklyWrite, get_weekly, store_weekly
from .transcription import MAX_AUDIO_BYTES, transcribe_audio

router = APIRouter(prefix="/api/v1/employee-reports", tags=["企业助手-员工日报"])


@router.post("", summary="提交口述日报 ENT-04（Dify 结构化后调用）")
def submit_report(
    payload: DailyReportCreate,
    db: Session = Depends(get_db),
    principal: EmployeePrincipal = Depends(require_employee),
):
    if payload.employee_id is None:
        payload = payload.model_copy(update={"employee_id": principal.employee_id})
    if payload.employee_id != principal.employee_id:
        raise HTTPException(403, "仅可提交本人日报")
    row = EmployeeReportService(db).submit(payload)
    return success(DailyReportOut.model_validate(row), "日报已提交")


@router.get("", summary="管理日报查阅 ENT-05")
def list_reports(
    employee_id: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    principal: EmployeePrincipal = Depends(require_employee),
):
    if employee_id is not None and employee_id != principal.employee_id:
        raise HTTPException(403, "无权查询他人日报")
    if date_from and date_to and date_from > date_to:
        raise HTTPException(422, "开始日期不能晚于结束日期")
    items = EmployeeReportService(db).list_reports(principal.employee_id, date_from, date_to)
    return success([DailyReportOut.model_validate(x) for x in items])


@router.post("/transcribe", summary="录制音频转写为日报草稿")
async def transcribe_report(file: UploadFile, principal: EmployeePrincipal = Depends(require_employee)):
    audio = await file.read(MAX_AUDIO_BYTES + 1)
    return success({"text": await transcribe_audio(audio)})


@router.get("/weekly")
def my_weekly(anchor: date, db: Session = Depends(get_db), principal: EmployeePrincipal = Depends(require_employee)):
    row = get_weekly(db, principal.employee_id, anchor)
    if row is None:
        return success(None)
    return success({key: getattr(row, key) for key in ("week_start", "content", "key_progress", "risks", "next_plan", "submitted_at")})


@router.put("/weekly")
def save_weekly(body: WeeklyWrite, db: Session = Depends(get_db), principal: EmployeePrincipal = Depends(require_employee)):
    return success(store_weekly(db, principal.employee_id, body))
