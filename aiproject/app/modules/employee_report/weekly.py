from datetime import date

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.modules.auth.models import accounts
from app.modules.statistics.periods import beijing_now, week_monday
from .models import WeeklySubmission


class WeeklyWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    anchor: date
    content: str = Field(min_length=1, max_length=8000)
    key_progress: str | None = Field(None, max_length=4000)
    risks: str | None = Field(None, max_length=4000)
    next_plan: str | None = Field(None, max_length=4000)


def get_weekly(db, employee_id, anchor):
    return db.get(WeeklySubmission, (employee_id, week_monday(anchor)))


def store_weekly(db, employee_id, body: WeeklyWrite):
    db.scalar(select(accounts.c.id).where(accounts.c.id == employee_id).with_for_update())
    start = week_monday(body.anchor)
    row = get_weekly(db, employee_id, body.anchor)
    if row is None:
        row = WeeklySubmission(employee_id=employee_id, week_start=start)
        db.add(row)
    for key, value in body.model_dump(exclude={"anchor"}).items():
        setattr(row, key, value)
    row.submitted_at = beijing_now()
    db.commit()
    return {"week_start": start}
