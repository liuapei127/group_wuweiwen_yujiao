from sqlalchemy.orm import Session

from app.ai.nl2sql.executor import Nl2SqlExecutor
from app.ai.nl2sql.schemas import Nl2SqlQuery
from app.ai.nl2sql.security import Nl2SqlSecurityError, validate_request


class Nl2SqlService:
    def __init__(self, db: Session):
        self.db = db

    def query(self, body: Nl2SqlQuery, actor_employee_id: int | None) -> dict:
        safe_params = validate_request(body.intent, dict(body.params), actor_employee_id)
        result = Nl2SqlExecutor(self.db).execute(body.intent, safe_params)
        return {"intent": body.intent, "result": result}
