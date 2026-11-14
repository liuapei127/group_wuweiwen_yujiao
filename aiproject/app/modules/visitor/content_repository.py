from sqlalchemy import select
from sqlalchemy.orm import Session

from .content_models import WebsiteSection, WebsiteSectionCard


def sections_and_cards(db: Session, *, published_only: bool):
    stmt = (
        select(WebsiteSection, WebsiteSectionCard)
        .outerjoin(
            WebsiteSectionCard,
            (WebsiteSectionCard.section_id == WebsiteSection.id)
            & (WebsiteSectionCard.published.is_(True) if published_only else True),
        )
        .order_by(WebsiteSection.sort_order, WebsiteSection.id, WebsiteSectionCard.sort_order, WebsiteSectionCard.id)
    )
    if published_only:
        stmt = stmt.where(WebsiteSection.published.is_(True))
    return db.execute(stmt)


def get_section(db: Session, section_id: int):
    return db.get(WebsiteSection, section_id)


def save_section(db: Session, values: dict, section_id: int | None):
    if section_id is None:
        section = WebsiteSection(**values)
        db.add(section)
    else:
        section = get_section(db, section_id)
        if section is not None:
            for field, value in values.items():
                setattr(section, field, value)
    return section


def save_card(db: Session, section_id: int, values: dict, card_id: int | None):
    if card_id is None:
        card = WebsiteSectionCard(section_id=section_id, **values)
        db.add(card)
    else:
        card = db.get(WebsiteSectionCard, card_id)
        if card is None or card.section_id != section_id:
            return None
        for field, value in values.items():
            setattr(card, field, value)
    return card
