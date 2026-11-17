from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Literal
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import BusinessError
from app.core.security.authorization import require_permission
from app.modules.auth.repository import AuthRepository
from .analysis_models import ReportRules
from .periods import beijing_now


class RuleSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    high_value_match_score: float | None = Field(None, ge=0, le=100)
    lead_inactive_days: int | None = Field(None, ge=1, le=365)
    complaint_overdue_days: int | None = Field(None, ge=1, le=365)
    complaint_escalate_days: int | None = Field(None, ge=1, le=365)
    reminder_repeat_days: int | None = Field(None, ge=1, le=90)
    psych_negative_days: int | None = Field(None, ge=2, le=30)
    psych_alert_level: Literal["low", "medium", "high"] | None = None
    project_complaint_weight: float | None = Field(None, ge=0, le=1)
    project_application_weight: float | None = Field(None, ge=0, le=1)
    project_deadline_weight: float | None = Field(None, ge=0, le=1)

    @model_validator(mode="after")
    def validate_weights(self):
        if (self.psych_negative_days is None) != (self.psych_alert_level is None):
            raise ValueError("自评提醒天数和待核验预警等级须同时设置")
        if self.complaint_escalate_days is not None:
            if self.complaint_overdue_days is None or self.complaint_escalate_days < self.complaint_overdue_days:
                raise ValueError("升级提醒天数须大于或等于投诉超时天数")
        weights = (self.project_complaint_weight, self.project_application_weight, self.project_deadline_weight)
        if any(value is not None for value in weights):
            if any(value is None for value in weights) or abs(sum(weights) - 1) > 0.000001:
                raise ValueError("三个项目评分权重须同时设置且合计为 1")
        return self


class RuleUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=0)
    settings: RuleSettings


def read_rules(db):
    row = db.get(ReportRules, 1)
    return {"version": row.version if row else 0,
            "settings": RuleSettings.model_validate(row.settings if row else {}).model_dump()}


def get_rules(db, principal):
    require_permission(principal, "users:manage")
    if principal.role_code != "admin":
        raise BusinessError(403, "仅管理员可以管理报表规则")
    return read_rules(db)


def update_rules(db, principal, body):
    get_rules(db, principal)
    try:
        row = db.get(ReportRules, 1, with_for_update=True)
        version = row.version if row else 0
        if body.expected_version != version:
            raise BusinessError(409, "规则已更新，请刷新后重试")
        if row is None:
            row = ReportRules(id=1)
            db.add(row)
        row.version = version + 1
        row.settings = body.settings.model_dump()
        row.updated_by = principal.employee_id
        row.updated_at = beijing_now()
        AuthRepository(db).audit(principal.employee_id, "report_rules_updated", 1,
                                 {"version": row.version, "settings": row.settings})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise BusinessError(409, "规则已更新，请刷新后重试") from exc
    except Exception:
        db.rollback()
        raise
    return read_rules(db)
