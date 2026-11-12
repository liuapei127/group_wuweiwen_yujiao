from typing import Any

from pydantic import BaseModel, Field, ConfigDict


class Nl2SqlQuery(BaseModel):
    """Dify 解析口语后的结构化请求；禁止传入 raw_sql。"""
    model_config = ConfigDict(extra="forbid")
    intent: str = Field(..., min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
