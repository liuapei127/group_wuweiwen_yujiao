from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class SectionWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    sort_order: int = Field(ge=0, le=9999)
    published: bool


class CardWrite(SectionWrite):
    content: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]


class PublicCard(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    content: str


class ManagedCard(PublicCard):
    sort_order: int
    published: bool


class PublicSection(BaseModel):
    id: int
    anchor: str
    title: str
    cards: list[PublicCard]


class ManagedSection(PublicSection):
    sort_order: int
    published: bool
    cards: list[ManagedCard]
