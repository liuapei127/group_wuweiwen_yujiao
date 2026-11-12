from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.ai.nl2sql.schemas import Nl2SqlQuery
from app.ai.nl2sql.security import Nl2SqlSecurityError
from app.ai.nl2sql.service import Nl2SqlService
from app.core.security import EmployeePrincipal, require_employee
from app.core.database import get_db
from app.core.responses import http_fail as fail, success
from app.modules.consultant.errors import ConflictError

router = APIRouter(prefix="/api/v1/ai/nl2sql", tags=["企业助手-NL2SQL"])


@router.post("/query", summary="只读 NL2SQL（ENT-11，禁止 raw SQL）")
def nl2sql_query(
    body: Nl2SqlQuery,
    db: Session = Depends(get_db),
    principal: EmployeePrincipal = Depends(require_employee),
):
    from app.core.security.authorization import require_permission
    from app.core.security.rbac import INTENT_PERMISSIONS
    if body.intent in INTENT_PERMISSIONS:
        require_permission(principal,INTENT_PERMISSIONS[body.intent])
    try:
        data = Nl2SqlService(db).query(body, principal.employee_id)
    except Nl2SqlSecurityError as e:
        return fail(str(e), code=403)
    except ConflictError as e:
        return fail(str(e), code=409)
    except ValueError as e:
        return fail(str(e), code=422)
    return success(data)
