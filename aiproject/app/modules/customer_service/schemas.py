from pydantic import BaseModel, ConfigDict, Field, StringConstraints
from typing import Annotated


class PublicChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: Annotated[str, StringConstraints(strip_whitespace=True)] = Field(min_length=1, max_length=4000)


class PublicChatReply(BaseModel):
    answer: str
