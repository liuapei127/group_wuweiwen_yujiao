from typing import Annotated

from fastapi import APIRouter, Depends, Path, Response
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import success
from app.core.security import EmployeePrincipal, require_employee

from . import content_service as service
from .content_schemas import CardWrite, SectionWrite

public_router = APIRouter(prefix="/api/v1/website", tags=["官网内容"])
staff_router = APIRouter(prefix="/api/v1/enterprise/website-content", tags=["官网内容管理"])
Database = Annotated[Session, Depends(get_db)]
RecordId = Annotated[int, Path(ge=1, le=2**63 - 1)]


def require_admin(employee: Annotated[EmployeePrincipal, Depends(require_employee)]):
    service.require_content_admin(employee)


@public_router.get("/sections")
def public_sections(db: Database, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return success(service.list_sections(db, published_only=True))


@staff_router.get("", dependencies=[Depends(require_admin)])
def managed_sections(db: Database, response: Response):
    response.headers["Cache-Control"] = "no-store"
    return success(service.list_sections(db, published_only=False))


@staff_router.post("", dependencies=[Depends(require_admin)], status_code=201)
def create_section(body: SectionWrite, db: Database):
    return success(service.save_section(db, body))


@staff_router.put("/{section_id}", dependencies=[Depends(require_admin)])
def update_section(section_id: RecordId, body: SectionWrite, db: Database):
    return success(service.save_section(db, body, section_id))


@staff_router.post("/{section_id}/cards", dependencies=[Depends(require_admin)], status_code=201)
def create_card(section_id: RecordId, body: CardWrite, db: Database):
    return success(service.save_card(db, section_id, body))


@staff_router.put("/{section_id}/cards/{card_id}", dependencies=[Depends(require_admin)])
def update_card(section_id: RecordId, card_id: RecordId, body: CardWrite, db: Database):
    return success(service.save_card(db, section_id, body, card_id))
