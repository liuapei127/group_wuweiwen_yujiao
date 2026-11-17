from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints


class ChatTurn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=500)


class PublicChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: Annotated[str, StringConstraints(strip_whitespace=True)] = Field(min_length=1, max_length=4000)
    session_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    start_session: bool = False
    history: list[ChatTurn] | None = Field(default=None, max_length=8)


class PublicChatReply(BaseModel):
    answer: str
    session_id: str | None = None
    reservation_changed: bool = False
