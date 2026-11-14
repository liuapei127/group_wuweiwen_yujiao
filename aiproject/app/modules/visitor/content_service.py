from sqlalchemy.orm import Session

from app.core.exceptions import BusinessError
from app.core.security import EmployeePrincipal

from . import content_repository
from .content_schemas import CardWrite, ManagedCard, ManagedSection, PublicCard, PublicSection, SectionWrite


def require_content_admin(employee: EmployeePrincipal):
    if employee.role_code != "admin":
        raise BusinessError(403, "仅管理员可以管理官网内容")


def list_sections(db: Session, *, published_only: bool):
    section_schema, card_schema = (PublicSection, PublicCard) if published_only else (ManagedSection, ManagedCard)
    sections = {}
    for section, card in content_repository.sections_and_cards(db, published_only=published_only):
        if section.id not in sections:
            sections[section.id] = section_schema(
                id=section.id, anchor=section.anchor or f"section-{section.id}", title=section.title,
                sort_order=section.sort_order, published=section.published, cards=[],
            )
        if card is not None:
            sections[section.id].cards.append(card_schema.model_validate(card))
    return list(sections.values())


def save_section(db: Session, payload: SectionWrite, section_id: int | None = None):
    section = content_repository.save_section(db, payload.model_dump(), section_id)
    if section is None:
        raise BusinessError(404, "栏目不存在")
    db.flush()
    result = {"id": section.id}
    db.commit()
    return result


def save_card(db: Session, section_id: int, payload: CardWrite, card_id: int | None = None):
    if content_repository.get_section(db, section_id) is None:
        raise BusinessError(404, "栏目不存在")
    card = content_repository.save_card(db, section_id, payload.model_dump(), card_id)
    if card is None:
        raise BusinessError(404, "该栏目下没有这张卡片")
    db.flush()
    result = {"id": card.id}
    db.commit()
    return result
