from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class TodoInput(Input):
    title: str = Field(min_length=1,max_length=255)
    description: str | None = Field(default=None,max_length=10000)
    due_time: datetime | None = None
    priority: Literal["low","medium","high","urgent"] = "medium"

class TodoUpdate(Input):
    expected_status: Literal["pending","in_progress","done","cancelled"]
    status: Literal["in_progress","done","cancelled"]
