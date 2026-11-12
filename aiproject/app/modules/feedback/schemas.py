from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class TicketUpdate(Input):
    expected_status: Literal["pending","processing","resolved","closed"]
    status: Literal["processing","resolved","closed"]
    solution: str | None = Field(default=None,max_length=10000)
