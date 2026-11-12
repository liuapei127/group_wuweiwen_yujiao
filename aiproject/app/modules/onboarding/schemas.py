from datetime import datetime
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class Input(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

class GuideInput(Input):
    title: str = Field(min_length=1,max_length=255)
    category: str = Field(min_length=1,max_length=64)
    content: str = Field(min_length=1,max_length=50000)
