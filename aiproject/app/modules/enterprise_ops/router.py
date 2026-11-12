from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.security import EmployeePrincipal, require_employee
from app.core.database import get_db
from app.modules.enterprise_ops.schemas import CommandRequest
from app.core.responses import success
from . import service

router = APIRouter(prefix="/api/v1/enterprise", tags=["企业助手-指令式处理"])


@router.post("/commands", summary="指令式写操作 ENT-12（Dify 解析后调用）")
def execute_command(
    body: CommandRequest,
    db: Session = Depends(get_db),
    principal: EmployeePrincipal = Depends(require_employee),
):
    result = service.execute_command(body, db, principal)
    return success(result.data, result.message)
